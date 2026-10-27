"""Use case thanh toán: trả tiền trực tiếp và nhận callback của cổng.

Hai đường vào đều dùng chung một hàm chốt đơn ``_settle``, nên trạng thái đơn,
trạng thái ghế và việc sinh vé không thể lệch nhau giữa hai luồng.
"""

from __future__ import annotations

from collections.abc import Callable

from app.domain.auth import Actor
from app.domain.entities import Order, OrderStatus, Payment, PaymentStatus, Ticket
from app.domain.errors import (
    IdempotencyKeyReused,
    InvalidState,
    NotFound,
    OrderExpired,
    SeatUnavailable,
    ValidationFailed,
)
from app.domain.ports import (
    PaymentGateway,
    TicketCodeGenerator,
    UnitOfWork,
)


class PaymentResult:
    def __init__(
        self,
        *,
        payment_id: int,
        order_id: int,
        amount: int,
        status: OrderStatus,
        ticket_codes: list[str],
        reused: bool,
    ) -> None:
        self.payment_id = payment_id
        self.order_id = order_id
        self.amount = amount
        self.status = status
        self.ticket_codes = ticket_codes
        self.reused = reused


class WebhookResult:
    """Kết quả xử lý callback. ``processed=False`` nghĩa là đã bỏ qua vì trùng."""

    def __init__(self, *, processed: bool, reason: str) -> None:
        self.processed = processed
        self.reason = reason


class PaymentService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        clock,
        gateway: PaymentGateway,
        code_gen: TicketCodeGenerator,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._gateway = gateway
        self._codes = code_gen

    # ------------------------------------------------------------------- pay
    def pay(self, actor: Actor, *, order_id: int, idempotency_key: str) -> PaymentResult:
        now = self._clock.now()

        # Bước 1: đọc và kiểm tra đơn trong một transaction ngắn, đóng lại
        # trước khi gọi cổng thanh toán.
        with self._uow() as uow:
            existing = uow.payments.get_by_idempotency(
                user_id=actor.id, idempotency_key=idempotency_key
            )
            if existing is not None:
                if existing.order_id != order_id:
                    raise IdempotencyKeyReused(
                        "Idempotency key was used for a different order"
                    )
                order = uow.orders.get(order_id)
                codes = uow.tickets.codes_for_order(order_id)
                return PaymentResult(
                    payment_id=existing.id,
                    order_id=order_id,
                    amount=existing.amount,
                    status=order.status if order else OrderStatus.PAID,
                    ticket_codes=codes,
                    reused=True,
                )

            order = uow.orders.get(order_id)
            if order is None or order.user_id != actor.id:
                raise NotFound("Order not found")
            if order.status is not OrderStatus.PENDING:
                raise InvalidState("Order is not pending")
            if order.expires_at <= now:
                if uow.orders.mark_expired(order_id, now=now):
                    uow.commit()
                raise OrderExpired("Order has expired")

        # Bước 2: gọi cổng thanh toán khi không còn transaction nào mở, để
        # không giữ connection trong lúc chờ I/O bên ngoài.
        response = self._gateway.charge(order_id=order_id, amount=order.total)
        gateway_status = response.get("status", "SUCCEEDED")
        provider_ref = response.get("provider_ref")

        # Bước 3: chốt kết quả trong một transaction mới.
        with self._uow() as uow:
            if gateway_status != "SUCCEEDED":
                uow.payments.add(
                    self._payment(
                        order=order,
                        user_id=actor.id,
                        idempotency_key=idempotency_key,
                        status=PaymentStatus.FAILED,
                        provider_ref=provider_ref,
                        response=response,
                    )
                )
                uow.commit()
                raise InvalidState("Payment failed")

            payment, codes = self._settle(
                uow,
                order=order,
                user_id=actor.id,
                idempotency_key=idempotency_key,
                provider_ref=provider_ref,
                response=response,
                now=now,
            )
            uow.commit()
            return PaymentResult(
                payment_id=payment.id,
                order_id=order_id,
                amount=order.total,
                status=OrderStatus.PAID,
                ticket_codes=codes,
                reused=False,
            )

    # --------------------------------------------------------------- webhook
    def handle_webhook(
        self, *, provider_ref: str, order_id: int, status: str, amount: int
    ) -> WebhookResult:
        """Xử lý callback của cổng thanh toán.

        Callback có thể đến nhiều lần cho cùng một giao dịch, hoặc đến sau khi
        người dùng đã tự gọi ``POST /orders/{id}/pay``. Cả hai trường hợp đều
        phải trả 200 mà không xử lý lại.
        """
        now = self._clock.now()
        with self._uow() as uow:
            # Chống replay: UNIQUE(provider_ref) là chốt chặn ở DB, còn phép
            # tra cứu này để trả 200 thay vì ném lỗi ràng buộc.
            if uow.payments.get_by_provider_ref(provider_ref) is not None:
                return WebhookResult(processed=False, reason="duplicate_provider_ref")

            order = uow.orders.get(order_id)
            if order is None:
                raise NotFound("Order not found")
            if order.total != amount:
                raise ValidationFailed("Amount does not match the order")

            if order.status is not OrderStatus.PENDING:
                # Đơn đã được chốt bằng đường khác, hoặc đã huỷ/quá hạn.
                return WebhookResult(
                    processed=False, reason=f"order_already_{order.status.value.lower()}"
                )

            if status != "SUCCEEDED":
                uow.payments.add(
                    self._payment(
                        order=order,
                        user_id=order.user_id,
                        idempotency_key=f"webhook:{provider_ref}",
                        status=PaymentStatus.FAILED,
                        provider_ref=provider_ref,
                        response={"status": status, "amount": amount},
                    )
                )
                uow.commit()
                return WebhookResult(processed=True, reason="payment_failed")

            self._settle(
                uow,
                order=order,
                user_id=order.user_id,
                idempotency_key=f"webhook:{provider_ref}",
                provider_ref=provider_ref,
                response={"status": status, "amount": amount},
                now=now,
            )
            uow.commit()
            return WebhookResult(processed=True, reason="order_paid")

    # ------------------------------------------------------------ internals
    def _settle(
        self,
        uow: UnitOfWork,
        *,
        order: Order,
        user_id: int,
        idempotency_key: str,
        provider_ref: str | None,
        response: dict,
        now,
    ) -> tuple[Payment, list[str]]:
        """Chuyển ghế sang SOLD, chốt đơn PAID và sinh vé.

        Điều kiện ``hold_id`` trong câu chuyển ghế là lý do cách xử lý hết hạn
        kiểu lazy vẫn an toàn: nếu hold đã hết hạn và người khác kịp giữ lại
        ghế thì không dòng nào được cập nhật, và cả giao dịch bị huỷ.
        """
        assert order.id is not None
        sold_ids = uow.event_seats.mark_sold_by_hold(hold_id=order.hold_id, now=now)
        if len(sold_ids) != len(order.items):
            uow.rollback()
            uow.payments.add(
                self._payment(
                    order=order,
                    user_id=user_id,
                    idempotency_key=idempotency_key,
                    status=PaymentStatus.FAILED,
                    provider_ref=provider_ref,
                    response={"reason": "seats_unavailable"},
                )
            )
            uow.commit()
            raise SeatUnavailable("Seats no longer held by this hold")

        if not uow.orders.mark_paid(order.id, now=now):
            uow.rollback()
            raise InvalidState("Order cannot be paid")

        tickets = uow.tickets.add_many(
            [
                Ticket(
                    id=None,
                    order_id=order.id,
                    event_seat_id=seat_id,
                    code=self._codes.new_code(),
                )
                for seat_id in sold_ids
            ]
        )
        payment = uow.payments.add(
            self._payment(
                order=order,
                user_id=user_id,
                idempotency_key=idempotency_key,
                status=PaymentStatus.SUCCEEDED,
                provider_ref=provider_ref,
                response=response,
            )
        )
        return payment, [t.code for t in tickets]

    @staticmethod
    def _payment(
        *,
        order: Order,
        user_id: int,
        idempotency_key: str,
        status: PaymentStatus,
        provider_ref: str | None,
        response: dict,
    ) -> Payment:
        assert order.id is not None
        return Payment(
            id=None,
            user_id=user_id,
            order_id=order.id,
            idempotency_key=idempotency_key,
            status=status,
            amount=order.total,
            provider_ref=provider_ref,
            response=response,
        )
