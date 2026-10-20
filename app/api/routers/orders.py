"""Đơn hàng. Cần đăng nhập; quyền sở hữu kiểm ở tầng service."""

from __future__ import annotations

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentActor, OrderServiceDep
from app.api.errors import error_responses
from app.api.schemas import (
    OrderDetailOut,
    OrderIn,
    OrderItemOut,
    OrderOut,
    Page,
)
from app.domain.entities import Order

router = APIRouter(prefix="/orders", tags=["orders"])


def _to_order_out(order: Order) -> OrderOut:
    return OrderOut(
        order_id=order.id,
        status=order.status,
        total=order.total,
        expires_at=order.expires_at,
    )


def _to_order_detail(order: Order) -> OrderDetailOut:
    return OrderDetailOut(
        order_id=order.id,
        status=order.status,
        total=order.total,
        expires_at=order.expires_at,
        event_id=order.event_id,
        created_at=order.created_at,
        items=[
            OrderItemOut(event_seat_id=it.event_seat_id, price=it.price)
            for it in order.items
        ],
    )


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
def create_order(
    payload: OrderIn, actor: CurrentActor, service: OrderServiceDep
) -> OrderOut:
    order = service.create(actor, hold_id=payload.hold_id)
    return _to_order_out(order)


@router.get(
    "/me",
    response_model=Page[OrderDetailOut],
    summary="Đơn của tôi (mới nhất trước)",
    description="`user_id` lấy từ token, không nhận từ query hay body.",
    responses=error_responses(401),
)
def list_my_orders(
    actor: CurrentActor,
    service: OrderServiceDep,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> Page[OrderDetailOut]:
    items, total = service.list_mine(actor, page=page, size=size)
    return Page[OrderDetailOut](
        items=[_to_order_detail(o) for o in items],
        total=total,
        page=page,
        size=size,
    )


@router.get(
    "/{order_id}",
    response_model=OrderDetailOut,
    summary="Chi tiết đơn",
    description="Chỉ chủ đơn hoặc ADMIN, người khác nhận 404.",
    responses=error_responses(401, 404),
)
def get_order(
    order_id: int, actor: CurrentActor, service: OrderServiceDep
) -> OrderDetailOut:
    order = service.get(actor, order_id)
    return _to_order_detail(order)


@router.delete(
    "/{order_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Huỷ đơn PENDING",
    description="Đơn chuyển CANCELLED, ghế HELD về AVAILABLE theo `hold_id`.",
    responses=error_responses(401, 404, 409),
)
def cancel_order(
    order_id: int, actor: CurrentActor, service: OrderServiceDep
) -> Response:
    service.cancel(actor, order_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
