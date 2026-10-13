"""Vé của khán giả và check-in của nhân viên soát vé."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.errors import NotImplementedYet, error_responses
from app.api.schemas import CheckInOut, TicketOut

me_router = APIRouter(prefix="/tickets", tags=["tickets"])
checkin_router = APIRouter(prefix="/tickets", tags=["tickets"])


@me_router.get(
    "/me",
    response_model=list[TicketOut],
    summary="Vé của tôi",
    responses=error_responses(401),
)
def list_my_tickets() -> list[TicketOut]:
    raise NotImplementedYet("GET /tickets/me")


@checkin_router.post(
    "/{code}/check-in",
    response_model=CheckInOut,
    summary="[Staff] Check-in vé",
    description=(
        "Cập nhật `checked_in_at = now()` với điều kiện `checked_in_at IS "
        "NULL`; 0 dòng cập nhật nghĩa là vé đã được check-in rồi → 409 kèm "
        "thời điểm check-in trước."
    ),
    responses=error_responses(401, 403, 404, 409),
)
def check_in(code: str) -> CheckInOut:
    raise NotImplementedYet("POST /tickets/{code}/check-in")
