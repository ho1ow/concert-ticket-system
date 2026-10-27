"""Use case đơn hàng: tạo đơn từ hold, xem, huỷ."""

from __future__ import annotations

from collections.abc import Callable

from app.domain.auth import Actor, Role
from app.domain.entities import Order, OrderItem, OrderStatus
from app.domain.errors import (
    HoldExpired,
    InvalidState,
    NotFound,
)
from app.domain.ports import UnitOfWork


class OrderService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        clock,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock

    def create(self, actor: Actor, *, hold_id: int) -> Order:
        now = self._clock.now()
        with self._uow() as uow:
            hold = uow.holds.get(hold_id)
            if hold is None or hold.user_id != actor.id:
                raise NotFound("Hold not found")
            if hold.status.value != "ACTIVE":
                raise InvalidState("Hold is not active")
            if hold.expires_at <= now:
                raise HoldExpired("Hold has expired")
            if not hold.seat_ids:
                raise InvalidState("Hold has no seats")

            event_seats = uow.event_seats.list_by_event(event_id=hold.event_id)
            seat_to_zone: dict[int, int] = {es.id: es.zone_id for es in event_seats}
            missing = [s for s in hold.seat_ids if s not in seat_to_zone]
            if missing:
                raise NotFound("Seats not found")

            zone_ids = sorted({seat_to_zone[s] for s in hold.seat_ids})
            zone_price = uow.event_zones.prices_for_event(
                event_id=hold.event_id, zone_ids=zone_ids
            )

            items: list[OrderItem] = []
            total = 0
            for es_id in hold.seat_ids:
                zone_id = seat_to_zone[es_id]
                price = zone_price.get(zone_id, 0)
                items.append(
                    OrderItem(
                        id=None,
                        order_id=None,
                        event_seat_id=es_id,
                        price=price,
                    )
                )
                total += price

            placeholder = Order(
                id=None,
                user_id=actor.id,
                event_id=hold.event_id,
                hold_id=hold.id,
                total=total,
                expires_at=hold.expires_at,
                status=OrderStatus.PENDING,
            )
            # Repository đã dịch vi phạm UNIQUE(hold_id) thành InvalidState,
            # nên ở đây không cần biết đến IntegrityError của SQLAlchemy.
            order = uow.orders.add(placeholder, items, now=now)

            converted = uow.holds.mark_converted(hold.id, now=now)
            if not converted:
                uow.rollback()
                raise InvalidState("Hold cannot be converted")

            uow.commit()
            order.items = items
            return order

    def get(self, actor: Actor, order_id: int) -> Order:
        with self._uow() as uow:
            order = uow.orders.get(order_id)
            if order is None:
                raise NotFound("Order not found")
            if actor.role is not Role.ADMIN and order.user_id != actor.id:
                raise NotFound("Order not found")
            return order

    def list_mine(
        self, actor: Actor, *, page: int, size: int
    ) -> tuple[list[Order], int]:
        with self._uow() as uow:
            return uow.orders.list_for_user_paginated(
                user_id=actor.id, page=page, size=size
            )

    def cancel(self, actor: Actor, order_id: int) -> None:
        now = self._clock.now()
        with self._uow() as uow:
            order = uow.orders.get(order_id)
            if order is None or order.user_id != actor.id:
                raise NotFound("Order not found")
            if order.status.value != "PENDING":
                raise InvalidState("Order is not pending")
            cancelled = uow.orders.mark_cancelled(order_id, now=now)
            if not cancelled:
                raise InvalidState("Order cannot be cancelled")
            uow.event_seats.release_held_by_hold(
                hold_id=order.hold_id, now=now
            )
            uow.commit()

