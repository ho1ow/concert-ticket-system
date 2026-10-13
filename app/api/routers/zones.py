"""Khu vực và sơ đồ ghế của một event."""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.api.errors import NotImplementedYet, error_responses
from app.api.schemas import EventSeatOut, ZoneIn, ZoneOut

read_router = APIRouter(prefix="/events", tags=["zones & seats"])
write_router = APIRouter(prefix="/events", tags=["zones & seats"])


@read_router.get(
    "/{event_id}/zones",
    response_model=list[ZoneOut],
    summary="Danh sách khu vực kèm số ghế còn trống",
    responses=error_responses(404),
)
def list_zones(event_id: int) -> list[ZoneOut]:
    raise NotImplementedYet("GET /events/{event_id}/zones")


@read_router.get(
    "/{event_id}/seats",
    response_model=list[EventSeatOut],
    summary="Sơ đồ ghế",
    description=(
        "Endpoint đọc chịu tải cao nhất. Lấy bằng một câu JOIN để tránh "
        "N+1. Ghế HELD đã quá `held_until` được trả về là AVAILABLE "
        "(lazy expiry)."
    ),
    responses=error_responses(404),
)
def list_event_seats(
    event_id: int,
    zone: str | None = Query(None, description="Lọc theo tên khu vực"),
) -> list[EventSeatOut]:
    raise NotImplementedYet("GET /events/{event_id}/seats")


@write_router.post(
    "/{event_id}/zones",
    response_model=ZoneOut,
    status_code=status.HTTP_201_CREATED,
    summary="[Admin] Tạo khu vực, gán giá và ghế",
    description=(
        "Chỉ làm được khi event đang DRAFT. UNIQUE(event_id, seat_id) trên "
        "`event_zone_seats` bảo đảm mỗi ghế thuộc tối đa một zone."
    ),
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_zone(event_id: int, payload: ZoneIn) -> ZoneOut:
    raise NotImplementedYet("POST /events/{event_id}/zones")
