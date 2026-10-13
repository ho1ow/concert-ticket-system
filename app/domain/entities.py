"""Thực thể nghiệp vụ, dạng dataclass, không dùng ORM.

Tiền lưu bằng ``int`` đơn vị VND. VND không có phần lẻ nên không cần Decimal,
và tránh được sai số của float.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from app.domain.auth import Role


class EventStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    CANCELLED = "CANCELLED"


class SeatStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    HELD = "HELD"
    SOLD = "SOLD"


class HoldStatus(str, Enum):
    ACTIVE = "ACTIVE"
    CONVERTED = "CONVERTED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class PaymentStatus(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


@dataclass(slots=True)
class User:
    id: int | None
    email: str
    password_hash: str
    role: Role = Role.USER
    is_active: bool = True
    failed_logins: int = 0
    locked_until: datetime | None = None
    created_at: datetime | None = None

    def is_locked(self, now: datetime) -> bool:
        return self.locked_until is not None and self.locked_until > now


@dataclass(slots=True)
class RefreshToken:
    id: int | None
    user_id: int
    token_hash: str
    family_id: str
    expires_at: datetime
    revoked_at: datetime | None = None
    replaced_by: int | None = None
    created_at: datetime | None = None

    def is_expired(self, now: datetime) -> bool:
        return self.expires_at <= now

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None


@dataclass(slots=True)
class Venue:
    id: int | None
    name: str
    address: str | None = None
    created_at: datetime | None = None


@dataclass(slots=True)
class Seat:
    """Ghế vật lý của địa điểm, không phụ thuộc event."""

    id: int | None
    venue_id: int
    section: str
    row: str
    number: int


@dataclass(slots=True)
class Event:
    id: int | None
    venue_id: int
    title: str
    description: str | None
    start_time: datetime
    sale_open_at: datetime
    status: EventStatus = EventStatus.DRAFT
    created_at: datetime | None = None

    def is_on_sale(self, now: datetime) -> bool:
        return self.status is EventStatus.PUBLISHED and now >= self.sale_open_at


@dataclass(slots=True)
class EventZone:
    """Khu vực của một event, mang giá vé."""

    id: int | None
    event_id: int
    name: str
    price: int


@dataclass(slots=True)
class EventSeat:
    """Ghế của một event, sinh ra lúc publish."""

    id: int | None
    event_id: int
    seat_id: int
    zone_id: int
    status: SeatStatus = SeatStatus.AVAILABLE
    hold_id: int | None = None
    held_until: datetime | None = None

    def effective_status(self, now: datetime) -> SeatStatus:
        """Lazy expiry: HELD đã quá hạn thì coi như AVAILABLE."""
        if self.status is SeatStatus.HELD and (
            self.held_until is None or self.held_until < now
        ):
            return SeatStatus.AVAILABLE
        return self.status


@dataclass(slots=True)
class Hold:
    id: int | None
    user_id: int
    event_id: int
    expires_at: datetime
    status: HoldStatus = HoldStatus.ACTIVE
    created_at: datetime | None = None
    seat_ids: list[int] = field(default_factory=list)

    def is_usable(self, now: datetime) -> bool:
        return self.status is HoldStatus.ACTIVE and self.expires_at > now


@dataclass(slots=True)
class OrderItem:
    id: int | None
    order_id: int | None
    event_seat_id: int
    price: int


@dataclass(slots=True)
class Order:
    id: int | None
    user_id: int
    event_id: int
    hold_id: int
    total: int
    expires_at: datetime
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime | None = None
    items: list[OrderItem] = field(default_factory=list)


@dataclass(slots=True)
class Payment:
    id: int | None
    user_id: int
    order_id: int
    idempotency_key: str
    status: PaymentStatus
    amount: int
    provider_ref: str | None = None
    response: dict | None = None
    created_at: datetime | None = None


@dataclass(slots=True)
class Ticket:
    id: int | None
    order_id: int
    event_seat_id: int
    code: str
    checked_in_at: datetime | None = None
    created_at: datetime | None = None
