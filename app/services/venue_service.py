"""Use case cho venue: list"""

from __future__ import annotations

from collections.abc import Callable

from app.domain.entities import Seat, Venue
from app.domain.errors import NotFound
from app.domain.ports import UnitOfWork


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

    def create_venue(self, name: str, address: str | None) -> Venue:
        """Tạo venue mới"""
        venue = Venue(id=None, name=name, address=address)
        with self._uow() as uow:
            venue = uow.venues.add(venue)
            uow.commit()
            return venue

    def create_seats(
        self,
        venue_id: int,
        ranges: list[tuple[str, str, int, int]],
    ) -> int:
        """Tạo ghế hàng loạt cho venue."""
        with self._uow() as uow:
            if uow.venues.get(venue_id) is None:
                raise NotFound(f"Venue {venue_id} does not exist")

            seats = [
                Seat(
                    id=None,
                    venue_id=venue_id,
                    section=section,
                    row=row,
                    number=number,
                )
                for section, row, first, last in ranges
                for number in range(first, last + 1)
            ]

            created = uow.seats.add_many(seats)
            uow.commit()
            return created
            
