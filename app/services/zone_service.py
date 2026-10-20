"""Use case tạo khu vực và gán ghế cho event."""

from __future__ import annotations

from collections.abc import Callable

from app.domain.entities import EventStatus, EventZone
from app.domain.errors import InvalidState, NotFound, SeatConflict
from app.domain.ports import UnitOfWork


class ZoneService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow = uow_factory

    def create_zone(
        self,
        event_id: int,
        name: str,
        price: int,
        seat_ids: list[int],
    ) -> EventZone:
        """Tạo khu vực mới cho event. Ghế phải thuộc event và chưa được gán."""
        if not seat_ids:
            raise InvalidState("Zone phải có ít nhất một ghế")

        if len(set(seat_ids)) != len(seat_ids):
            raise InvalidState("Một seat chỉ xuất hiện một lần trong danh sách seat_ids")

        with self._uow() as uow:
            event = uow.events.get_for_update(event_id)
            if event is None:
                raise NotFound("Event không tồn tại")

            if event.status != EventStatus.DRAFT:
                raise InvalidState("Chỉ được tạo khu vực khi event còn DRAFT")

            seats = uow.seats.list_by_ids(seat_ids)
            if len(seats) != len(seat_ids):
                raise NotFound("Một hoặc nhiều ghế không tồn tại")

            if any(seat.venue_id != event.venue_id for seat in seats):
                raise InvalidState("Ghế phải thuộc venue của event")

            assigned = uow.event_zones.assigned_seat_ids(event_id, seat_ids)
            if assigned:
                raise InvalidState("Một hoặc nhiều ghế đã thuộc zone khác")

            zone = uow.event_zones.add(
                EventZone(
                    id=None,
                    event_id=event_id,
                    name=name,
                    price=price,
                )
            )

            assert zone.id is not None
            uow.event_zones.assign_seats(
                event_id=event_id,
                zone_id=zone.id,
                seat_ids=seat_ids,
            )

            uow.commit()
            return zone
        