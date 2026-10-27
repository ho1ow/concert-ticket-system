"""Pydantic schema cho request/response.

Tất cả schema đầu vào dùng ``extra="forbid"``: field lạ bị từ chối 422 thay
vì bị bỏ qua. Đây là lớp chặn mass assignment, ví dụ gửi kèm
``"role": "ADMIN"`` khi register.

Tiền là ``int`` đơn vị VND.
"""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.domain.auth import Role
from app.domain.entities import (
    Event,
    EventStatus,
    HoldStatus,
    OrderStatus,
    Seat,
    SeatStatus,
    User,
    Venue,
)

T = TypeVar("T")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int


class ErrorOut(BaseModel):
    """Hình dạng chung của mọi response lỗi."""

    error: str = Field(examples=["SEAT_UNAVAILABLE"])
    message: str
    details: dict | None = None


# ----------------------------------------------------------------- auth
class RegisterIn(StrictModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class LoginIn(StrictModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class RefreshIn(StrictModel):
    refresh_token: str = Field(min_length=1)


class UserOut(BaseModel):
    id: int
    email: str

    @classmethod
    def from_entity(cls, user: User) -> UserOut:
        return cls(id=user.id, email=user.email)


class MeOut(BaseModel):
    id: int
    email: str
    role: Role
    is_active: bool

    @classmethod
    def from_entity(cls, user: User) -> MeOut:
        return cls(
            id=user.id, email=user.email, role=user.role, is_active=user.is_active
        )


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Số giây còn hiệu lực của access token")


# ---------------------------------------------------------------- venues
class VenueIn(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    address: str | None = Field(default=None, max_length=500)


class VenueOut(BaseModel):
    id: int
    name: str
    address: str | None = None

    @classmethod
    def from_entity(cls, venue: Venue) -> VenueOut:
        return cls(id=venue.id, name=venue.name, address=venue.address)


class SeatRangeIn(StrictModel):
    """Một dải ghế liên tiếp trong cùng hàng."""

    section: str = Field(min_length=1, max_length=32)
    row: str = Field(min_length=1, max_length=16)
    from_: int = Field(alias="from", ge=1)
    to: int = Field(ge=1)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode="after")
    def validate_range(self) -> SeatRangeIn:
        if self.to < self.from_:
            raise ValueError("'to' phải lớn hơn hoặc bằng 'from'")
        return self


class SeatBulkIn(StrictModel):
    ranges: list[SeatRangeIn] = Field(min_length=1)


class SeatOut(BaseModel):
    id: int
    section: str
    row: str
    number: int

    @classmethod
    def from_entity(cls, seat: Seat) -> SeatOut:
        return cls(id=seat.id, section=seat.section, row=seat.row, number=seat.number)


class SeatBulkOut(BaseModel):
    created: int


# ---------------------------------------------------------------- events
class EventIn(StrictModel):
    venue_id: int
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    start_time: datetime
    sale_open_at: datetime


class EventUpdateIn(StrictModel):
    """Khi event đã PUBLISHED chỉ còn sửa được title/description."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    start_time: datetime | None = None
    sale_open_at: datetime | None = None
    venue_id: int | None = None


class EventOut(BaseModel):
    id: int
    venue_id: int
    title: str
    description: str | None
    start_time: datetime
    sale_open_at: datetime
    status: EventStatus

    @classmethod
    def from_entity(cls, event: Event) -> EventOut:
        return cls(
            id=event.id,
            venue_id=event.venue_id,
            title=event.title,
            description=event.description,
            start_time=event.start_time,
            sale_open_at=event.sale_open_at,
            status=event.status,
        )


class ZoneIn(StrictModel):
    name: str = Field(min_length=1, max_length=64)
    price: int = Field(ge=0, description="Giá vé, đơn vị VND")
    seat_ids: list[int] = Field(min_length=1)


class ZoneOut(BaseModel):
    id: int
    name: str
    price: int
    available_seats: int | None = None


class EventDetailOut(EventOut):
    zones: list[ZoneOut] = []


class EventSeatOut(BaseModel):
    """Một ô trên sơ đồ ghế. ``status`` đã áp dụng lazy expiry."""

    event_seat_id: int
    section: str
    row: str
    number: int
    zone: str
    price: int
    status: SeatStatus


class PublishOut(BaseModel):
    id: int
    status: EventStatus
    event_seats_created: int


# ----------------------------------------------------------------- holds
class HoldIn(StrictModel):
    event_id: int
    seat_ids: list[int] = Field(min_length=1, max_length=4)


class HoldOut(BaseModel):
    hold_id: int
    event_id: int
    seat_ids: list[int]
    expires_at: datetime


class HoldDetailOut(HoldOut):
    status: HoldStatus
    seconds_left: int


# ---------------------------------------------------------------- orders
class OrderIn(StrictModel):
    hold_id: int


class OrderItemOut(BaseModel):
    event_seat_id: int
    price: int


class OrderOut(BaseModel):
    order_id: int
    status: OrderStatus
    total: int
    expires_at: datetime


class OrderDetailOut(OrderOut):
    event_id: int
    created_at: datetime | None = None
    items: list[OrderItemOut] = []


# -------------------------------------------------------------- payments
class PayOut(BaseModel):
    order_id: int
    status: OrderStatus
    payment_id: int
    amount: int
    ticket_codes: list[str] = []


class WebhookIn(BaseModel):
    """Payload của cổng thanh toán giả lập.

    Không dùng ``extra="forbid"``: cổng thanh toán có thể thêm field mới.
    Tính xác thực đến từ HMAC trên raw body, không từ hình dạng JSON.
    """

    provider_ref: str
    order_id: int
    status: str
    amount: int


class WebhookAck(BaseModel):
    received: bool = True
    processed: bool = True
    reason: str = ""


# --------------------------------------------------------------- tickets
class TicketOut(BaseModel):
    id: int
    code: str
    event_id: int
    event_title: str
    section: str
    row: str
    number: int
    checked_in_at: datetime | None = None


class CheckInOut(BaseModel):
    code: str
    checked_in_at: datetime


