"""SQLAlchemy models: toàn bộ schema của hệ thống.

Các bất biến nghiệp vụ được DB bảo vệ bằng UNIQUE, CHECK và FK, không chỉ
bằng code ứng dụng. Xem docs/details.md §3.1.

Enum lưu dạng VARCHAR kèm CHECK (``native_enum=False``) để không phải tạo
type riêng trong Postgres và schema dễ tái tạo.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

from app.domain.auth import Role
from app.domain.entities import (
    EventStatus,
    HoldStatus,
    OrderStatus,
    PaymentStatus,
    SeatStatus,
)

JsonCol = JSON().with_variant(JSONB(), "postgresql")


def _enum(py_enum, name: str) -> Enum:
    # create_constraint=True để DB sinh CHECK kiểm giá trị hợp lệ; mặc định của
    # SQLAlchemy là False, khi đó cột chỉ còn là VARCHAR không ràng buộc.
    return Enum(
        py_enum,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=16,
        validate_strings=True,
    )


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# --------------------------------------------------------------------- auth
class UserModel(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(
        _enum(Role, "role"), nullable=False, default=Role.USER
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshTokenModel(TimestampMixin, Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    family_id: Mapped[str] = mapped_column(String(36), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by: Mapped[int | None] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL")
    )

    __table_args__ = (
        Index("ix_refresh_tokens_user", "user_id"),
        Index("ix_refresh_tokens_family", "family_id"),
    )


# ------------------------------------------------------------------- venues
class VenueModel(TimestampMixin, Base):
    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500))


class SeatModel(Base):
    """Ghế vật lý của địa điểm."""

    __tablename__ = "seats"

    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(
        ForeignKey("venues.id", ondelete="CASCADE"), nullable=False
    )
    section: Mapped[str] = mapped_column(String(32), nullable=False)
    row: Mapped[str] = mapped_column(String(16), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "venue_id", "section", "row", "number", name="uq_seat_in_venue"
        ),
        Index("ix_seats_venue", "venue_id"),
    )


# ------------------------------------------------------------------- events
class EventModel(TimestampMixin, Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sale_open_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[EventStatus] = mapped_column(
        _enum(EventStatus, "event_status"), nullable=False, default=EventStatus.DRAFT
    )

    __table_args__ = (
        CheckConstraint("start_time > sale_open_at", name="ck_event_sale_before_start"),
        Index("ix_events_status_start", "status", "start_time"),
    )


class EventZoneModel(Base):
    """Khu vực của event, mang giá vé (VND, số nguyên)."""

    __tablename__ = "event_zones"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint("event_id", "name", name="uq_zone_name_in_event"),
        CheckConstraint("price >= 0", name="ck_zone_price_non_negative"),
    )


class EventZoneSeatModel(Base):
    """Gán ghế vật lý vào zone, làm ở trạng thái DRAFT.

    UNIQUE(event_id, seat_id) bảo đảm mỗi ghế thuộc tối đa một zone.
    """

    __tablename__ = "event_zone_seats"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    zone_id: Mapped[int] = mapped_column(
        ForeignKey("event_zones.id", ondelete="CASCADE"), nullable=False
    )
    seat_id: Mapped[int] = mapped_column(
        ForeignKey("seats.id", ondelete="CASCADE"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("event_id", "seat_id", name="uq_seat_single_zone"),
        Index("ix_zone_seats_zone", "zone_id"),
    )


class EventSeatModel(Base):
    """Ghế của một event, sinh ra lúc publish.

    Giữ ghế bằng UPDATE có điều kiện trên bảng này. Xem docs/details.md §3.
    """

    __tablename__ = "event_seats"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    seat_id: Mapped[int] = mapped_column(ForeignKey("seats.id"), nullable=False)
    zone_id: Mapped[int] = mapped_column(ForeignKey("event_zones.id"), nullable=False)
    status: Mapped[SeatStatus] = mapped_column(
        _enum(SeatStatus, "seat_status"), nullable=False, default=SeatStatus.AVAILABLE
    )
    hold_id: Mapped[int | None] = mapped_column(
        ForeignKey("holds.id", ondelete="SET NULL")
    )
    held_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("event_id", "seat_id", name="uq_event_seat"),
        Index("ix_event_seats_event_zone", "event_id", "zone_id"),
        Index("ix_event_seats_hold", "hold_id"),
    )


# -------------------------------------------------------------------- holds
class HoldModel(TimestampMixin, Base):
    __tablename__ = "holds"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    status: Mapped[HoldStatus] = mapped_column(
        _enum(HoldStatus, "hold_status"), nullable=False, default=HoldStatus.ACTIVE
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_holds_user_event_status", "user_id", "event_id", "status"),
    )


# ------------------------------------------------------------------- orders
class OrderModel(TimestampMixin, Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    # UNIQUE: một hold chỉ sinh được một đơn.
    hold_id: Mapped[int] = mapped_column(
        ForeignKey("holds.id"), unique=True, nullable=False
    )
    status: Mapped[OrderStatus] = mapped_column(
        _enum(OrderStatus, "order_status"), nullable=False, default=OrderStatus.PENDING
    )
    total: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_orders_user_created", "user_id", "created_at"),)


class OrderItemModel(Base):
    """Giá được chốt tại thời điểm tạo đơn, không đọc lại giá lúc thanh toán."""

    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    event_seat_id: Mapped[int] = mapped_column(
        ForeignKey("event_seats.id"), nullable=False
    )
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint("order_id", "event_seat_id", name="uq_order_item_seat"),
        Index("ix_order_items_order", "order_id"),
    )


# ----------------------------------------------------------------- payments
class PaymentModel(TimestampMixin, Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        _enum(PaymentStatus, "payment_status"), nullable=False
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    provider_ref: Mapped[str | None] = mapped_column(String(128), unique=True)
    response: Mapped[dict | None] = mapped_column(JsonCol)

    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_payment_idempotency"),
    )


# ------------------------------------------------------------------ tickets
class TicketModel(TimestampMixin, Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    # UNIQUE: một ghế chỉ có một vé, kể cả khi code ứng dụng có bug.
    event_seat_id: Mapped[int] = mapped_column(
        ForeignKey("event_seats.id"), unique=True, nullable=False
    )
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_tickets_order", "order_id"),)
