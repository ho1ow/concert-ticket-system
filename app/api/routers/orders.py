"""Đơn hàng. Cần đăng nhập; quyền sở hữu kiểm ở tầng service."""

from __future__ import annotations

from fastapi import APIRouter, Query, Response, status

from app.api.errors import NotImplementedYet, error_responses
from app.api.schemas import OrderDetailOut, OrderIn, OrderOut, Page

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post(
    "",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
    summary="Tạo đơn từ một hold",
    description=(
        "Hold phải thuộc chính mình, đang ACTIVE và còn hạn. Tổng tiền chốt "
        "theo giá zone tại thời điểm tạo đơn và lưu vào `order_items.price`, "
        "không đọc lại giá lúc thanh toán. UNIQUE(hold_id) bảo đảm một hold "
        "chỉ sinh được một đơn."
    ),
    responses=error_responses(401, 404, 410, 422),
)
def create_order(payload: OrderIn) -> OrderOut:
    raise NotImplementedYet("POST /orders")


@router.get(
    "/me",
    response_model=Page[OrderDetailOut],
    summary="Đơn của tôi (mới nhất trước)",
    description="`user_id` lấy từ token, không nhận từ query hay body.",
    responses=error_responses(401),
)
def list_my_orders(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> Page[OrderDetailOut]:
    raise NotImplementedYet("GET /orders/me")


@router.get(
    "/{order_id}",
    response_model=OrderDetailOut,
    summary="Chi tiết đơn",
    description="Chỉ chủ đơn hoặc ADMIN, người khác nhận 404.",
    responses=error_responses(401, 404),
)
def get_order(order_id: int) -> OrderDetailOut:
    raise NotImplementedYet("GET /orders/{order_id}")


@router.delete(
    "/{order_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Huỷ đơn PENDING",
    description="Đơn chuyển CANCELLED, ghế HELD về AVAILABLE theo `hold_id`.",
    responses=error_responses(401, 404, 409),
)
def cancel_order(order_id: int) -> Response:
    raise NotImplementedYet("DELETE /orders/{order_id}")
