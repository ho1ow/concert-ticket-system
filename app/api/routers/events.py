"""Concert. Đọc là public (chỉ thấy PUBLISHED), ghi là ADMIN."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query, Response, status

from app.api.errors import NotImplementedYet, error_responses
from app.api.schemas import (
    EventDetailOut,
    EventIn,
    EventOut,
    EventUpdateIn,
    Page,
    PublishOut,
)
from app.domain.entities import EventStatus

read_router = APIRouter(prefix="/events", tags=["events"])
write_router = APIRouter(prefix="/events", tags=["events"])


@read_router.get(
    "",
    response_model=Page[EventOut],
    summary="Danh sách concert",
    description="Endpoint đọc chịu tải cao. Public chỉ thấy event PUBLISHED.",
)
def list_events(
    status_filter: EventStatus | None = Query(None, alias="status"),
    date_from: datetime | None = Query(None, alias="from"),
    date_to: datetime | None = Query(None, alias="to"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> Page[EventOut]:
    raise NotImplementedYet("GET /events")


@read_router.get(
    "/{event_id}",
    response_model=EventDetailOut,
    summary="Chi tiết concert kèm zone và giá",
    responses=error_responses(404),
)
def get_event(event_id: int) -> EventDetailOut:
    raise NotImplementedYet("GET /events/{event_id}")


@write_router.post(
    "",
    response_model=EventOut,
    status_code=status.HTTP_201_CREATED,
    summary="[Admin] Tạo concert (DRAFT)",
    description="Bắt buộc `start_time > sale_open_at > now`.",
    responses=error_responses(401, 403, 422),
)
def create_event(payload: EventIn) -> EventOut:
    raise NotImplementedYet("POST /events")


@write_router.put(
    "/{event_id}",
    response_model=EventOut,
    summary="[Admin] Sửa concert",
    description="Sửa tự do khi DRAFT. Khi đã PUBLISHED chỉ còn title và description.",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_event(event_id: int, payload: EventUpdateIn) -> EventOut:
    raise NotImplementedYet("PUT /events/{event_id}")


@write_router.delete(
    "/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="[Admin] Xoá concert (chỉ khi DRAFT)",
    responses=error_responses(401, 403, 404, 409),
)
def delete_event(event_id: int) -> Response:
    raise NotImplementedYet("DELETE /events/{event_id}")


@write_router.post(
    "/{event_id}/publish",
    response_model=PublishOut,
    summary="[Admin] Mở bán, sinh event_seats",
    description=(
        "Điều kiện: event đang DRAFT, có ít nhất 1 zone, mọi ghế của venue đã "
        "được gán zone. Trong một transaction: sinh `event_seats` trạng thái "
        "AVAILABLE cho toàn bộ ghế, rồi chuyển event sang PUBLISHED."
    ),
    responses=error_responses(401, 403, 404, 409),
)
def publish_event(event_id: int) -> PublishOut:
    raise NotImplementedYet("POST /events/{event_id}/publish")
