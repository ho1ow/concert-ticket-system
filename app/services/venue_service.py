"""Use case cho venue: list"""

from __future__ import annotations

from collections.abc import Callable

from app.domain.entities import Venue
from app.domain.ports import UnitOfWork


class VenueService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow = uow_factory

    def list_venues(self, page: int, size: int) -> tuple[list[Venue], int]:
        """Trả về danh sách venue và tổng số venue."""
        with self._uow() as uow:
            venues, total = uow.venues.list(page, size)
            return venues, total
