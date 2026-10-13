"""Map lỗi nghiệp vụ sang HTTP status.

Tầng domain và services chỉ raise ``DomainError`` kèm một ``code``, bảng dưới
đây quyết định status tương ứng. Thêm lỗi mới chỉ cần thêm một dòng.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.errors import DomainError


STATUS_BY_CODE: dict[str, int] = {
    # 400
    "MISSING_IDEMPOTENCY_KEY": 400,
    # 401
    "UNAUTHORIZED": 401,
    "INVALID_CREDENTIALS": 401,
    "INVALID_REFRESH_TOKEN": 401,
    # 403 / 404
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    # 409
    "EMAIL_EXISTS": 409,
    "SEAT_UNAVAILABLE": 409,
    "SALE_NOT_OPEN": 409,
    "INVALID_STATE": 409,
    "ALREADY_CHECKED_IN": 409,
    # 410
    "HOLD_EXPIRED": 410,
    "ORDER_EXPIRED": 410,
    # 422
    "LIMIT_EXCEEDED": 422,
    "IDEMPOTENCY_KEY_REUSED": 422,
    "VALIDATION_ERROR": 422,
    # 429 (Pha 2)
    "RATE_LIMITED": 429,
}

DEFAULT_STATUS = 500


def error_body(code: str, message: str, details: dict | None = None) -> dict:
    body: dict = {"error": code, "message": message}
    if details:
        body["details"] = details
    return body


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        status = STATUS_BY_CODE.get(exc.code, DEFAULT_STATUS)
        headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
        return JSONResponse(
            status_code=status,
            content=error_body(exc.code, exc.message, exc.details),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_body(
                "VALIDATION_ERROR",
                "Request validation failed",
                {"errors": _safe_errors(exc)},
            ),
        )


def _safe_errors(exc: RequestValidationError) -> list[dict]:
    """Bỏ ``input``/``ctx`` khỏi chi tiết lỗi để không vọng lại mật khẩu."""
    out = []
    for err in exc.errors():
        out.append(
            {
                "loc": [str(part) for part in err.get("loc", [])],
                "type": err.get("type"),
                "msg": err.get("msg"),
            }
        )
    return out


class NotImplementedYet(Exception):
    """Khung endpoint đã có, phần nghiệp vụ chưa code.

    Đặt ở tầng api vì domain không cần biết khái niệm này.
    """

    def __init__(self, what: str) -> None:
        self.what = what
        super().__init__(f"{what} is not implemented yet")


def register_stub_handler(app: FastAPI) -> None:
    @app.exception_handler(NotImplementedYet)
    async def _not_implemented(_: Request, exc: NotImplementedYet) -> JSONResponse:
        return JSONResponse(
            status_code=501,
            content=error_body("NOT_IMPLEMENTED", str(exc), {"endpoint": exc.what}),
        )


def error_responses(*codes: int) -> dict:
    """Khai báo response lỗi cho OpenAPI, dùng chung một schema ErrorOut."""
    from app.api.schemas import ErrorOut

    labels = {
        400: "Thiếu tham số bắt buộc",
        401: "Chưa xác thực",
        403: "Sai role",
        404: "Không tồn tại hoặc không phải của mình",
        409: "Xung đột trạng thái",
        410: "Quá hạn",
        422: "Vi phạm quy tắc nghiệp vụ / dữ liệu sai",
        429: "Bị giới hạn tần suất",
        501: "Chưa triển khai",
    }
    return {c: {"model": ErrorOut, "description": labels.get(c, "Lỗi")} for c in codes}
