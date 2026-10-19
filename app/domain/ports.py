"""Interface mà tầng services phụ thuộc vào.

Tầng services chỉ biết các Protocol ở đây, nên test được bằng fake
implementation, không cần DB, JWT thật hay thư viện hash.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from app.domain.auth import AccessToken, Actor
from app.domain.entities import (
    Event,
    EventSeat,
    Hold,
    Order,
    OrderItem,
    Payment,
    RefreshToken,
    Ticket,
    User,
)


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime:
        """Thời điểm hiện tại, luôn timezone-aware (UTC)."""
        ...


@runtime_checkable
class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...

    def dummy_verify(self, password: str) -> None:
        ...


@runtime_checkable
class TokenIssuer(Protocol):
    def issue_access(self, actor: Actor) -> AccessToken: ...

    def decode_access(self, token: str) -> Actor:
        ...

    def new_refresh_token(self) -> tuple[str, str]:
        ...

    def hash_refresh_token(self, raw: str) -> str: ...


@runtime_checkable
class TicketCodeGenerator(Protocol):
    def new_code(self) -> str: ...


@runtime_checkable
class PaymentGateway(Protocol):
    def charge(self, *, order_id: int, amount: int) -> dict:
        ...


@runtime_checkable
class EventRepository(Protocol):
    def get(self, event_id: int) -> Event | None: ...

    def list_paginated(
        self,
        *,
        status: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int,
        size: int,
        include_drafts: bool = False,
    ) -> tuple[list[Event], int]: ...

    def add(self, event: Event) -> Event: ...

    def update(self, event: Event) -> None: ...

    def delete(self, event_id: int) -> bool: ...


@runtime_checkable
class EventSeatRepository(Protocol):
    def get(self, event_seat_id: int) -> EventSeat | None: ...

    def list_by_event(
        self, event_id: int, *, zone_id: int | None = None
    ) -> list[EventSeat]: ...

    def count_zones_seats(self, event_id: int) -> int: ...

    def list_with_seat(
        self,
        *,
        event_id: int,
        zone_id: int | None = None,
    ) -> list[tuple[Any, Any]]: ...

    def zones_with_meta(self, event_id: int) -> dict[int, tuple[str, int]]: ...

    def lock_seats_atomically(
        self,
        *,
        event_id: int,
        seat_ids: list[int],
        hold_id: int,
        now: datetime,
        new_held_until: datetime,
    ) -> list[int]:
        ...

    def release_held_by_hold(
        self, *, hold_id: int, now: datetime
    ) -> int:
        ...

    def mark_sold_by_hold(
        self, *, hold_id: int, now: datetime
    ) -> list[int]:
        ...

    def add_many(self, items: list[EventSeat]) -> None: ...


@runtime_checkable
class EventZoneRepository(Protocol):
    def get(self, zone_id: int) -> Any | None: ...

    def prices_for_event(self, event_id: int, zone_ids: list[int]) -> dict[int, int]:
        ...

    def list_by_event(self, event_id: int) -> list[Any]: ...


@runtime_checkable
class HoldRepository(Protocol):
    def add(self, hold: Hold, *, now: datetime) -> Hold: ...

    def get(self, hold_id: int) -> Hold | None: ...

    def list_for_user_event_active(
        self, *, user_id: int, event_id: int, now: datetime
    ) -> list[Hold]: ...

    def seat_ids_in_hold(self, hold_id: int) -> list[int]: ...

    def mark_released(self, hold_id: int, *, now: datetime) -> bool: ...

    def mark_converted(self, hold_id: int, *, now: datetime) -> bool: ...


@runtime_checkable
class OrderRepository(Protocol):
    def get(self, order_id: int) -> Order | None: ...

    def list_for_user_paginated(
        self, *, user_id: int, page: int, size: int
    ) -> tuple[list[Order], int]: ...

    def add(self, order: Order, items: list[OrderItem], *, now: datetime) -> Order: ...

    def mark_paid(self, order_id: int, *, now: datetime) -> bool: ...

    def mark_cancelled(self, order_id: int, *, now: datetime) -> bool: ...

    def mark_expired(self, order_id: int, *, now: datetime) -> bool: ...

    def items_of(self, order_id: int) -> list[OrderItem]: ...

    def order_items_by_event_seat(
        self, *, user_id: int, event_id: int
    ) -> list[OrderItem]: ...


@runtime_checkable
class PaymentRepository(Protocol):
    def get_by_idempotency(
        self, *, user_id: int, idempotency_key: str
    ) -> Payment | None: ...

    def add(self, payment: Payment) -> Payment: ...


@runtime_checkable
class TicketRepository(Protocol):
    def add_many(self, tickets: list[Ticket]) -> list[Ticket]: ...

    def list_for_user(self, *, user_id: int) -> list[Ticket]: ...

    def get_by_code(self, code: str) -> Ticket | None: ...

    def check_in(
        self, *, code: str, now: datetime
    ) -> Ticket | None: ...

    def codes_for_order(self, order_id: int) -> list[str]: ...

    def list_with_details_for_user(
        self, *, user_id: int
    ) -> list[tuple[Any, Any, Any]]: ...


@runtime_checkable
class UserRepository(Protocol):
    def get(self, user_id: int) -> User | None: ...

    def get_by_email(self, email: str) -> User | None: ...

    def add(self, user: User) -> User:
        ...

    def update(self, user: User) -> None: ...


@runtime_checkable
class RefreshTokenRepository(Protocol):
    def add(self, token: RefreshToken) -> RefreshToken: ...

    def get_by_hash(self, token_hash: str) -> RefreshToken | None: ...

    def revoke(
        self, token_id: int, *, now: datetime, replaced_by: int | None = None
    ) -> bool:
        ...

    def revoke_family(self, family_id: str, *, now: datetime) -> int:
        ...


@runtime_checkable
class UnitOfWork(Protocol):
    users: UserRepository
    refresh_tokens: RefreshTokenRepository
    events: EventRepository
    event_seats: EventSeatRepository
    event_zones: EventZoneRepository
    holds: HoldRepository
    orders: OrderRepository
    payments: PaymentRepository
    tickets: TicketRepository

    def __enter__(self) -> UnitOfWork: ...

    def __exit__(self, exc_type, exc, tb) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    @property
    def session(self): ...

    def advisory_xact_lock(self, key1: int, key2: int) -> None: ...
