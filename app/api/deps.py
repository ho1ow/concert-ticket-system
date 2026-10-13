"""Xác thực tập trung và nơi lắp dependency.

Chứa lớp kiểm tra token và lớp kiểm tra role. Các file router không tự kiểm
tra token hay role.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.domain.auth import Actor, Role
from app.domain.errors import Forbidden, Unauthorized
from app.infra.config import Settings, get_settings
from app.infra.db.uow import SqlAlchemyUnitOfWork
from app.infra.security import Argon2Hasher, JwtTokenIssuer, SystemClock
from app.services.auth_service import AuthService

# auto_error=False để tự trả lỗi theo đúng bảng mã lỗi của hệ thống.
bearer_scheme = HTTPBearer(auto_error=False, description="Access token (JWT HS256)")


# ------------------------------------------------------------- providers
@lru_cache
def get_password_hasher() -> Argon2Hasher:
    return Argon2Hasher()


@lru_cache
def get_token_issuer() -> JwtTokenIssuer:
    settings = get_settings()
    return JwtTokenIssuer(
        secret=settings.jwt_secret,
        issuer=settings.jwt_issuer,
        access_ttl_seconds=settings.access_token_ttl_seconds,
    )


@lru_cache
def get_clock() -> SystemClock:
    return SystemClock()


def get_uow_factory():
    return SqlAlchemyUnitOfWork


@lru_cache
def get_auth_service() -> AuthService:
    settings = get_settings()
    return AuthService(
        uow_factory=SqlAlchemyUnitOfWork,
        hasher=get_password_hasher(),
        tokens=get_token_issuer(),
        clock=get_clock(),
        refresh_ttl_days=settings.refresh_token_ttl_days,
        lock_threshold=settings.login_lock_threshold,
        lock_minutes=settings.login_lock_minutes,
    )


# ------------------------------------------------------- authentication
def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
    issuer: Annotated[JwtTokenIssuer, Depends(get_token_issuer)] = None,
) -> Actor:
    """Dựng Actor từ access token.

    Không query DB ở bước này để đường đi vẫn nhanh khi tải cao. Vì vậy user
    bị khoá hoặc đổi role vẫn dùng được access token cũ cho tới khi token hết
    hạn, tối đa 15 phút.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise Unauthorized("Missing bearer token")
    return issuer.decode_access(credentials.credentials)


def require_role(*roles: str):
    """Chặn theo role. Gắn ở cấp nhóm router trong main.py."""
    allowed = {Role(role) for role in roles}

    def dependency(actor: Annotated[Actor, Depends(get_current_user)]) -> Actor:
        if actor.role not in allowed:
            raise Forbidden("Insufficient role")
        return actor

    return dependency


# ------------------------------------------------------------- shortcuts
CurrentActor = Annotated[Actor, Depends(get_current_user)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
