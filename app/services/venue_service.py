"""Use case cho venue: list"""

from __future__ import annotations

from collections.abc import Callable

from app.domain.entities import Venue, Seat
from app.domain.ports import UnitOfWork
from app.domain.errors import NotFound

class VenueService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow = uow_factory

    def list_venues(self, page: int, size: int) -> tuple[list[Venue], int]:
        """Trả về danh sách venue và tổng số venue."""
        with self._uow() as uow:
            venues, total = uow.venues.list(page, size)
            return venues, total

    def get_venue(self, venue_id: int) -> Venue | None:
        """Trả về venue theo id, hoặc None nếu không tồn tại."""
        with self._uow() as uow:
            venue = uow.venues.get(venue_id)
            if venue is None: 
                raise NotFound(f"Venue {venue_id} không tồn tại")
            return venue

    def list_seats(self, venue_id: int, page: int, size: int) -> tuple[list[Seat], int]:
        """Trả về danh sách ghế của venue và tổng số ghế."""
        with self._uow() as uow:
            seats, total = uow.venues.list_seats(venue_id, page, size)
            return seats, total
