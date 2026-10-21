"""Use case đọc event cho khán giả và lấy sơ đồ ghế."""

from __future__ import annotations
from typing import Any

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from app.domain.auth import Actor, Role
from app.domain.entities import Event, EventSeat, EventStatus, EventZone, SeatStatus
from app.domain.errors import NotFound, InvalidState
from app.domain.ports import UnitOfWork


@dataclass
class EventZoneWithCount:
    zone: EventZone
    available_seats: int


class EventService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        clock,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock

    def list_published(
        self,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Event], int]:
        with self._uow() as uow:
            return uow.events.list_paginated(
                status=None,
                date_from=date_from,
                date_to=date_to,
                page=page,
                size=size,
                include_drafts=False,
            )

    def list_for_admin(
        self,
        *,
        status: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Event], int]:
        with self._uow() as uow:
            return uow.events.list_paginated(
                status=status,
                date_from=date_from,
                date_to=date_to,
                page=page,
                size=size,
                include_drafts=True,
            )

    def get_with_zones(
        self, actor: Actor, event_id: int
    ) -> tuple[Event, list[EventZoneWithCount]]:
        with self._uow() as uow:
            event = uow.events.get(event_id)
            if event is None:
                raise NotFound("Event not found")
            if (
                actor.role is not Role.ADMIN
                and event.status is not EventStatus.PUBLISHED
            ):
                raise NotFound("Event not found")
            zones = self._zones_with_counts(uow, event_id)
            return event, zones

    def zones(self, actor: Actor, event_id: int) -> list[EventZoneWithCount]:
        with self._uow() as uow:
            event = uow.events.get(event_id)
            if event is None:
                raise NotFound("Event not found")
            if (
                actor.role is not Role.ADMIN
                and event.status is not EventStatus.PUBLISHED
            ):
                raise NotFound("Event not found")
            return self._zones_with_counts(uow, event_id)

    def list_event_seats(
        self,
        actor: Actor,
        event_id: int,
        *,
        zone_id: int | None = None,
    ) -> list[tuple[EventSeat, Any]]:
        with self._uow() as uow:
            event = uow.events.get(event_id)
            if event is None:
                raise NotFound("Event not found")
            if (
                actor.role is not Role.ADMIN
                and event.status is not EventStatus.PUBLISHED
            ):
                raise NotFound("Event not found")
            return uow.event_seats.list_with_seat(
                event_id=event_id, zone_id=zone_id
            )

    def zones_meta(self, event_id: int) -> dict[int, tuple[str, int]]:
        with self._uow() as uow:
            return uow.event_seats.zones_with_meta(event_id=event_id)

    def _zones_with_counts(
        self, uow: UnitOfWork, event_id: int
    ) -> list[EventZoneWithCount]:
        zones_rows = uow.event_zones.list_by_event(event_id=event_id)
        seats = uow.event_seats.list_by_event(event_id=event_id)
        now = self._clock.now()
        result: list[EventZoneWithCount] = []
        for row in zones_rows:
            available = 0
            for es in seats:
                if es.zone_id != row.id:
                    continue
                if es.status.value == "AVAILABLE":
                    available += 1
                elif es.status.value == "HELD":
                    if es.held_until is None or es.held_until > now:
                        continue
                    available += 1
            zone = EventZone(
                id=row.id,
                event_id=row.event_id,
                name=row.name,
                price=row.price,
            )
            result.append(
                EventZoneWithCount(zone=zone, available_seats=available)
            )
        return result

    def create_event(
            self, 
            venue_id: int, 
            title: str, 
            description: str | None, 
            start_time: datetime, 
            sale_open_at: datetime) -> Event:
        with self._uow() as uow:
            venue = uow.venues.get(venue_id)
            if venue is None:
                raise NotFound("Không tìm thấy venue")

            now = self._clock.now()
            if sale_open_at <= now or start_time <= sale_open_at:
                raise ValueError("start_time phải > sale_open_at > now")
            
            event = Event(
                id=None,
                venue_id=venue_id,
                title=title,
                description=description,
                start_time=start_time,
                sale_open_at=sale_open_at,
                status=EventStatus.DRAFT,
            )
            event = uow.events.add(event)
            uow.commit()
            return event

    def publish_event(self, event_id: int) -> tuple[Event, int]:
        with self._uow() as uow:
            event = uow.events.get_for_update(event_id)
            if event is None:
                raise NotFound("Không tìm thấy event")

            if event.status is not EventStatus.DRAFT:
                raise InvalidState("Chỉ có thể publish event đang ở trạng thái DRAFT")

            zones = uow.event_zones.list_by_event(event_id)
            if not zones:
                raise InvalidState("Event phải có ít nhất một zone")

            # Kiểm tra mọi ghế của venue đã được gán zone
            page_size = 500
            seats, total = uow.venues.list_seats(
                event.venue_id,
                page=1,
                size=page_size,
            )

            total_pages = (total + page_size - 1) // page_size
            for page in range(2, total_pages + 1):
                page_seats, _ = uow.venues.list_seats(
                    event.venue_id,
                    page=page,
                    size=page_size,
                )
                seats.extend(page_seats)

            venue_seat_ids = {seat.id for seat in seats}
            if not venue_seat_ids:
                raise InvalidState("Venue phải có ít nhất một ghế")

            seat_zone_map = uow.event_zones.seat_zone_map(event_id)
            zone_ids = {zone.id for zone in zones}

            if (
                None in venue_seat_ids
                or set(seat_zone_map) != venue_seat_ids
                or not set(seat_zone_map.values()).issubset(zone_ids)
            ):
                raise InvalidState(
                    "Mọi ghế của venue phải được gán vào zone của event"
                )

            if uow.event_seats.count_zones_seats(event_id) > 0:
                raise InvalidState("Event đã có event_seats")

            event_seats = [
                EventSeat(
                    id=None,
                    event_id=event_id,
                    seat_id=seat_id,
                    zone_id=zone_id,
                    status=SeatStatus.AVAILABLE,
                )
                for seat_id, zone_id in sorted(seat_zone_map.items())
            ]

            uow.event_seats.add_many(event_seats)

            event.status = EventStatus.PUBLISHED
            uow.events.update(event)

            uow.commit()
            return event, len(event_seats)