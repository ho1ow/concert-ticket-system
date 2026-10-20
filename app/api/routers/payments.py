"""Thanh toán: endpoint trả tiền (JWT) và webhook của cổng (HMAC)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Header, Request

from app.api.deps import CurrentActor, PaymentServiceDep, SettingsDep
from app.api.errors import error_responses
from app.api.schemas import PayOut, WebhookAck
from app.domain.errors import MissingIdempotencyKey, Unauthorized
from app.infra.config import Settings
from app.infra.security import verify_webhook_signature

router = APIRouter(prefix="/orders", tags=["payments"])
webhook_router = APIRouter(prefix="/payments", tags=["payments"])


@router.post(
    "/{order_id}/pay",
    response_model=PayOut,
    summary="Thanh toán đơn (idempotent)",
    description=(
        "Bắt buộc có header `Idempotency-Key`. Cùng một key và cùng order thì "
        "trả lại đúng response cũ; cùng key nhưng khác order thì 422 "
        "`IDEMPOTENCY_KEY_REUSED`.\n\n"
        "ADMIN cũng không được trả tiền hộ người khác. Gọi cổng thanh toán "
        "xong mới mở transaction để chốt: order PENDING→PAID, ghế HELD→SOLD "
        "chỉ cho ghế còn đúng `hold_id` này, rồi sinh vé với mã QR ngẫu nhiên."
    ),
    responses=error_responses(400, 401, 404, 409, 410, 422),
)
def pay_order(
    order_id: int,
    actor: CurrentActor,
    service: PaymentServiceDep,
    idempotency_key: str | None = Header(
        None, alias="Idempotency-Key", description="Khoá idempotent do client sinh"
    ),
) -> PayOut:
    if not idempotency_key:
        raise MissingIdempotencyKey("Header Idempotency-Key is required")
    result = service.pay(
        actor, order_id=order_id, idempotency_key=idempotency_key
    )
    return PayOut(
        order_id=result.order_id,
        status=result.status,
        payment_id=result.payment_id,
        amount=result.amount,
        ticket_codes=result.ticket_codes,
    )


@webhook_router.post(
    "/webhook",
    response_model=WebhookAck,
    summary="Callback của cổng thanh toán (không dùng JWT)",
    description=(
        "Xác thực bằng `X-Signature = HMAC-SHA256(secret, timestamp + '.' + "
        "raw_body)`, so sánh thời gian hằng, lệch giờ quá 5 phút thì từ chối. "
        "Phải verify trên raw body trước khi parse JSON. UNIQUE(provider_ref) "
        "khiến nhận lại cùng một callback trả 200 mà không xử lý lại."
    ),
    responses=error_responses(401, 422),
)
async def payment_webhook(
    request: Request,
    settings: SettingsDep,
    x_signature: str | None = Header(None, alias="X-Signature"),
    x_timestamp: str | None = Header(None, alias="X-Timestamp"),
) -> WebhookAck:
    if not x_signature or not x_timestamp:
        raise Unauthorized("Missing webhook signature")
    body = await request.body()
    verify_webhook_signature(
        body=body,
        timestamp=x_timestamp,
        signature=x_signature,
        secret=settings.webhook_secret,
        max_skew=settings.webhook_max_skew_seconds,
    )
    try:
        json.loads(body or b"{}")
    except json.JSONDecodeError:
        raise Unauthorized("Malformed webhook payload")
    return WebhookAck(received=True)
