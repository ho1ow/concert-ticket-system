"""Use case thanh toán: pay (idempotent).

Phần cổng thanh toán đơn giản hoá: luôn thành công (xem infra/payment_gateway.py).
"""

from __future__ import annotations

from collections.abc import Callable

from app.domain.auth import Actor
from app.domain.entities import OrderStatus, Payment, PaymentStatus, Ticket
from app.domain.errors import (
    IdempotencyKeyReused,
    InvalidState,
    NotFound,
    OrderExpired,
    SeatUnavailable,
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

    def pay(self, actor: Actor, *, order_id: int, idempotency_key: str) -> PaymentResult:
        now = self._clock.now()

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
            if order.status.value != "PENDING":
                raise InvalidState("Order is not pending")
            if order.expires_at <= now:
                expired = uow.orders.mark_expired(order_id, now=now)
                if expired:
                    uow.commit()
                raise OrderExpired("Order has expired")

            payment_response = self._gateway.charge(
                order_id=order_id, amount=order.total
            )
            gateway_status = payment_response.get("status", "SUCCEEDED")
            provider_ref = payment_response.get("provider_ref")

            if gateway_status != "SUCCEEDED":
                failed = Payment(
                    id=None,
                    user_id=actor.id,
                    order_id=order_id,
                    idempotency_key=idempotency_key,
                    status=PaymentStatus.FAILED,
                    amount=order.total,
                    provider_ref=provider_ref,
                    response=payment_response,
                )
                uow.payments.add(failed)
                uow.commit()
                raise InvalidState("Payment failed")

            sold_ids = uow.event_seats.mark_sold_by_hold(
                hold_id=order.hold_id, now=now
            )
            if len(sold_ids) != len(order.items):
                uow.rollback()
                refunded = Payment(
                    id=None,
                    user_id=actor.id,
                    order_id=order_id,
                    idempotency_key=idempotency_key,
                    status=PaymentStatus.FAILED,
                    amount=order.total,
                    provider_ref=provider_ref,
                    response={"reason": "seats_unavailable"},
                )
                uow.payments.add(refunded)
                uow.commit()
                raise SeatUnavailable("Seats no longer held by this hold")

            paid = uow.orders.mark_paid(order_id, now=now)
            if not paid:
                uow.rollback()
                raise InvalidState("Order cannot be paid")

            codes = [self._codes.new_code() for _ in sold_ids]
            ticket_seed = [
                Ticket(
                    id=None,
                    order_id=order_id,
                    event_seat_id=es_id,
                    code=code,
                )
                for es_id, code in zip(sold_ids, codes)
            ]
            tickets = uow.tickets.add_many(ticket_seed)

            payment = Payment(
                id=None,
                user_id=actor.id,
                order_id=order_id,
                idempotency_key=idempotency_key,
                status=PaymentStatus.SUCCEEDED,
                amount=order.total,
                provider_ref=provider_ref,
                response=payment_response,
            )
            saved = uow.payments.add(payment)
            uow.commit()
            return PaymentResult(
                payment_id=saved.id,
                order_id=order_id,
                amount=order.total,
                status=OrderStatus.PAID,
                ticket_codes=[t.code for t in tickets],
                reused=False,
            )
