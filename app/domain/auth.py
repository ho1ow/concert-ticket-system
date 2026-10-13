"""Vai trò, chủ thể hành động và kiểm tra quyền sở hữu."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.domain.errors import Forbidden, NotFound


class Role(str, Enum):
    USER = "USER"
    STAFF = "STAFF"
    ADMIN = "ADMIN"


@dataclass(frozen=True, slots=True)
class Actor:
    """Chủ thể gọi API, dựng từ access token. Không query DB."""

    id: int
    role: Role

    @property
    def is_admin(self) -> bool:
        return self.role is Role.ADMIN

    @property
    def is_staff(self) -> bool:
        return self.role in (Role.STAFF, Role.ADMIN)


@dataclass(frozen=True, slots=True)
class AccessToken:
    token: str
    expires_in: int


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"


def ensure_owner(actor: Actor, owner_id: int, *, admin_can_read: bool = False) -> None:
    """Kiểm tra quyền sở hữu tài nguyên.

    Trả 404 thay vì 403 để không tiết lộ tài nguyên của người khác có tồn tại.
    """
    if actor.id == owner_id:
        return
    if admin_can_read and actor.is_admin:
        return
    raise NotFound("Resource not found")


def ensure_role(actor: Actor, *roles: Role) -> None:
    if actor.role not in roles:
        raise Forbidden("Insufficient role")
