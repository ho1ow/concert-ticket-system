"""Use case giữ ghế, nhả ghế, xem chi tiết hold.

Nguyên tắc:
- Khoá theo cặp (user_id, event_id) để chống 5 request song song lọt giới hạn.
- Chiếm ghế bằng UPDATE có điều kiện, so số dòng cập nhật với số ghế yêu cầu.
- Lazy expiry: ghế HELD có held_until <= now coi như AVAILABLE.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

from app.domain.auth import Actor
from app.domain.entities import Hold, HoldStatus
from app.domain.errors import (
    InvalidState,
    LimitExceeded,
    NotFound,
    SaleNotOpen,
    SeatUnavailable,
)
from app.domain.ports import UnitOfWork


class HoldService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        clock,
        *,
        hold_ttl_minutes: int = 10,
        max_seats_per_user: int = 4,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._ttl = timedelta(minutes=hold_ttl_minutes)
        self._max = max_seats_per_user

    def create(self, actor: Actor, *, event_id: int, seat_ids: list[int]) -> Hold:
        if not seat_ids:
            raise SeatUnavailable("Seat list is empty")
        unique = sorted(set(seat_ids))
        if len(unique) > self._max:
            raise LimitExceeded("Too many seats")
        if len(unique) != len(seat_ids):
            raise SeatUnavailable("Duplicate seat ids")

        now = self._clock.now()
        new_held_until = now + self._ttl

        with self._uow() as uow:
            event = uow.events.get(event_id)
            if event is None:
                raise NotFound("Event not found")
            if event.status.value != "PUBLISHED":
                raise InvalidState("Event is not published")
            if now < event.sale_open_at:
                raise SaleNotOpen("Sale is not open yet")

            uow.advisory_xact_lock(actor.id, event_id)

            held = uow.holds.list_for_user_event_active(
                user_id=actor.id, event_id=event_id, now=now
            )
            held_seat_count = sum(len(h.seat_ids) for h in held)
            owned_items = uow.orders.order_items_by_event_seat(
                user_id=actor.id, event_id=event_id
            )
            if held_seat_count + len(owned_items) + len(unique) > self._max:
                raise LimitExceeded("Per-user seat limit exceeded")

            placeholder = Hold(
                id=None,
                user_id=actor.id,
                event_id=event_id,
                expires_at=new_held_until,
                status=HoldStatus.ACTIVE,
            )
            hold = uow.holds.add(placeholder, now=now)

            locked = uow.event_seats.lock_seats_atomically(
                event_id=event_id,
                seat_ids=unique,
                hold_id=hold.id,
                now=now,
                new_held_until=new_held_until,
            )
            if len(locked) != len(unique):
                uow.rollback()
                owned = set(locked)
                missing = [s for s in unique if s not in owned]
                raise SeatUnavailable(
                    "Some seats are no longer available",
                    missing=missing,
                )

            hold.seat_ids = sorted(locked)
            uow.commit()
            return hold

    def get(self, actor: Actor, hold_id: int) -> Hold:
        with self._uow() as uow:
            hold = uow.holds.get(hold_id)
            if hold is None or hold.user_id != actor.id:
                raise NotFound("Hold not found")
            return hold

    def release(self, actor: Actor, hold_id: int) -> None:
        now = self._clock.now()
        with self._uow() as uow:
            hold = uow.holds.get(hold_id)
            if hold is None or hold.user_id != actor.id:
                raise NotFound("Hold not found")
            if hold.status.value != "ACTIVE":
                raise InvalidState("Hold is not active")
            released = uow.holds.mark_released(hold_id, now=now)
            if not released:
                raise InvalidState("Hold is not active")
            uow.event_seats.release_held_by_hold(hold_id=hold_id, now=now)
            uow.commit()
