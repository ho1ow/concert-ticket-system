"""Lắp router theo nhóm quyền và gắn exception handler.

Quyền gắn ở cấp nhóm router, nên các file router không tự kiểm tra token
hay role.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI

from app.api.deps import get_current_user, require_role
from app.api.errors import register_exception_handlers, register_stub_handler
from app.api.routers import (
    auth,
    events,
    holds,
    orders,
    payments,
    stats,
    tickets,
    venues,
    zones,
)
from app.infra.config import get_settings
from app.infra.db.session import init_schema

OPENAPI_DESCRIPTION = """
Dịch vụ backend đặt vé concert.

**Vai trò**: `USER` (khán giả) · `STAFF` (soát vé) · `ADMIN` (ban tổ chức).
ADMIN có quyền của STAFF; STAFF và ADMIN đều mua vé được như USER.

**Luồng chính**: `GET /events` → `GET /events/{id}/seats` → `POST /holds`
(giữ ghế 10 phút) → `POST /orders` → `POST /orders/{id}/pay` →
`GET /tickets/me` → `POST /tickets/{code}/check-in`.

**Mã lỗi**: mọi lỗi trả về `{"error": "<CODE>", "message": "...", "details": {...}}`.

**Xác thực**: `Authorization: Bearer <access_token>` (JWT HS256, 15 phút).
Webhook thanh toán không dùng JWT mà xác thực bằng HMAC-SHA256 trên raw body.
"""

TAGS_METADATA = [
    {"name": "auth", "description": "Đăng ký, đăng nhập, xoay vòng refresh token."},
    {"name": "venues", "description": "Địa điểm và ghế vật lý."},
    {"name": "events", "description": "Concert và vòng đời DRAFT → PUBLISHED."},
    {"name": "zones & seats", "description": "Khu vực, giá vé và sơ đồ ghế."},
    {"name": "holds", "description": "Giữ ghế tạm."},
    {"name": "orders", "description": "Đơn hàng."},
    {"name": "payments", "description": "Thanh toán idempotent và webhook."},
    {"name": "tickets", "description": "Vé QR và check-in."},
    {"name": "admin stats", "description": "Thống kê cho ban tổ chức."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.auto_create_schema:
        init_schema()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Concert Ticket System API",
        version="1.0.0",
        description=OPENAPI_DESCRIPTION,
        openapi_tags=TAGS_METADATA,
        lifespan=lifespan,
    )

    register_exception_handlers(app)
    register_stub_handler(app)

    # --- 4 nhóm quyền ---
    public = APIRouter()
    protected = APIRouter(dependencies=[Depends(get_current_user)])
    staff = APIRouter(dependencies=[Depends(require_role("STAFF", "ADMIN"))])
    admin = APIRouter(dependencies=[Depends(require_role("ADMIN"))])

    public.include_router(auth.public_router)
    public.include_router(venues.read_router)
    public.include_router(events.read_router)
    public.include_router(zones.read_router)

    protected.include_router(auth.me_router)
    protected.include_router(holds.router)
    protected.include_router(orders.router)
    protected.include_router(payments.router)
    protected.include_router(tickets.me_router)

    staff.include_router(tickets.checkin_router)

    admin.include_router(venues.write_router)
    admin.include_router(events.write_router)
    admin.include_router(zones.write_router)
    admin.include_router(stats.router)

    for group in (public, protected, staff, admin):
        app.include_router(group)

    # Webhook tự xác thực bằng HMAC, không thuộc nhóm nào.
    app.include_router(payments.webhook_router)

    @app.get("/health", tags=["ops"], summary="Health check")
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
