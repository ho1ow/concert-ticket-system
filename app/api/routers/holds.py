"""Giữ ghế. Cần đăng nhập."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.errors import NotImplementedYet, error_responses
from app.api.schemas import HoldDetailOut, HoldIn, HoldOut

router = APIRouter(prefix="/holds", tags=["holds"])


@router.post(
    "",
    response_model=HoldOut,
    status_code=status.HTTP_201_CREATED,
    summary="Giữ ghế tạm (TTL 10 phút)",
    description=(
        "Endpoint ghi chịu tải cao nhất. Quy tắc: 1 đến 4 ghế, không trùng id, "
        "cùng một event; event phải PUBLISHED và đã đến `sale_open_at`; tối đa 4 ghế "
        "mỗi user mỗi event (tính cả hold còn hạn và vé đã mua).\n\n"
        "Chiếm ghế bằng một câu UPDATE có điều kiện rồi so số dòng cập nhật "
        "với số ghế yêu cầu, theo nguyên tắc tất cả hoặc không, không giữ "
        "được một phần."
    ),
    responses=error_responses(401, 404, 409, 422),
)
def create_hold(payload: HoldIn) -> HoldOut:
    raise NotImplementedYet("POST /holds")


@router.get(
    "/{hold_id}",
    response_model=HoldDetailOut,
    summary="Thời gian còn lại của hold",
    description="Chỉ chủ hold xem được, người khác nhận 404 chứ không phải 403.",
    responses=error_responses(401, 404),
)
def get_hold(hold_id: int) -> HoldDetailOut:
    raise NotImplementedYet("GET /holds/{hold_id}")


@router.delete(
    "/{hold_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Nhả ghế",
    description="Hold chuyển RELEASED, ghế HELD về AVAILABLE theo đúng `hold_id`.",
    responses=error_responses(401, 404, 409),
)
def release_hold(hold_id: int) -> Response:
    raise NotImplementedYet("DELETE /holds/{hold_id}")
