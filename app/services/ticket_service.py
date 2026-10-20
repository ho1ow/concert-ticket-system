"""Use case vé: xem vé của tôi, check-in vé."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.domain.auth import Actor, Role
from app.domain.entities import Ticket
from app.domain.errors import (
    AlreadyCheckedIn,
    InvalidState,
    NotFound,
)
from app.domain.ports import UnitOfWork


@dataclass
class TicketDetail:
    ticket: Ticket
    event: Any
    seat: Any


class CheckInResult:
    def __init__(self, *, ticket: Ticket, already_checked_in: bool = False) -> None:
        self.ticket = ticket
        self.already_checked_in = already_checked_in


class TicketService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        clock,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock

    def list_for_user(self, actor: Actor) -> list[TicketDetail]:
        with self._uow() as uow:
            return [
                TicketDetail(ticket=t, event=e, seat=s)
                for t, e, s in uow.tickets.list_with_details_for_user(
                    user_id=actor.id
                )
            ]

    def check_in(self, actor: Actor, code: str) -> CheckInResult:
        now = self._clock.now()
        with self._uow() as uow:
            existing = uow.tickets.get_by_code(code)
            if existing is not None and existing.checked_in_at is not None:
                raise AlreadyCheckedIn(
                    "Ticket already checked in",
                    checked_in_at=existing.checked_in_at,
                )
            if existing is None:
                raise NotFound("Ticket not found")

            if actor.role is not Role.STAFF and actor.role is not Role.ADMIN:
                raise InvalidState("Cannot check-in")

            updated = uow.tickets.check_in(code=code, now=now)
            if updated is None:
                ticket = uow.tickets.get_by_code(code)
                if ticket is None:
                    raise NotFound("Ticket not found")
                raise AlreadyCheckedIn(
                    "Ticket already checked in",
                    checked_in_at=ticket.checked_in_at,
                )
            uow.commit()
            return CheckInResult(ticket=updated)
