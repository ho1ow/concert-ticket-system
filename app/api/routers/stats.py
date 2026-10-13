"""Thống kê cho ban tổ chức."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.errors import NotImplementedYet, error_responses
from app.api.schemas import EventStatsOut

router = APIRouter(prefix="/admin", tags=["admin stats"])


@router.get(
    "/events/{event_id}/stats",
    response_model=EventStatsOut,
    summary="[Admin] Thống kê bán / giữ / trống và doanh thu",
    description=(
        "Đếm ghế theo trạng thái (HELD đã quá hạn tính là trống), doanh thu "
        "lấy từ các đơn PAID, tách theo từng zone."
    ),
    responses=error_responses(401, 403, 404),
)
def event_stats(event_id: int) -> EventStatsOut:
    raise NotImplementedYet("GET /admin/events/{event_id}/stats")
