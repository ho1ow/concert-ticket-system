"""Lỗi nghiệp vụ. Thuần Python, không phụ thuộc HTTP.

Mỗi lỗi mang một ``code`` theo bảng mã lỗi trong docs. Việc map code sang
HTTP status nằm ở ``app/api/errors.py``.
"""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    """Gốc của mọi lỗi nghiệp vụ."""

    code: str = "DOMAIN_ERROR"

    def __init__(self, message: str | None = None, **details: Any) -> None:
        self.message = message or self.code
        self.details = details
        super().__init__(self.message)


# --- 401 ---
class Unauthorized(DomainError):
    code = "UNAUTHORIZED"


class InvalidCredentials(Unauthorized):
    code = "INVALID_CREDENTIALS"


class InvalidRefreshToken(Unauthorized):
    code = "INVALID_REFRESH_TOKEN"


# --- 403 / 404 ---
class Forbidden(DomainError):
    code = "FORBIDDEN"


class NotFound(DomainError):
    code = "NOT_FOUND"


# --- 409 ---
class EmailExists(DomainError):
    code = "EMAIL_EXISTS"


class InvalidState(DomainError):
    code = "INVALID_STATE"


class SeatUnavailable(DomainError):
    code = "SEAT_UNAVAILABLE"


class SaleNotOpen(DomainError):
    code = "SALE_NOT_OPEN"


class AlreadyCheckedIn(DomainError):
    code = "ALREADY_CHECKED_IN"

class SeatConflict(DomainError):
    code = "SEAT_CONFLICT"

# --- 410 ---
class HoldExpired(DomainError):
    code = "HOLD_EXPIRED"


class OrderExpired(DomainError):
    code = "ORDER_EXPIRED"


# --- 400 / 422 ---
class MissingIdempotencyKey(DomainError):
    code = "MISSING_IDEMPOTENCY_KEY"


class LimitExceeded(DomainError):
    code = "LIMIT_EXCEEDED"


class IdempotencyKeyReused(DomainError):
    code = "IDEMPOTENCY_KEY_REUSED"
