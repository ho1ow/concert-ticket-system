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
from app.infra.payment_gateway import FakePaymentGateway
from app.infra.security import (
    Argon2Hasher,
    JwtTokenIssuer,
    SystemClock,
    TicketCodeService,
)
from app.services.auth_service import AuthService
from app.services.venue_service import VenueService
from app.services.event_service import EventService
from app.services.hold_service import HoldService
from app.services.order_service import OrderService
from app.services.payment_service import PaymentService
from app.services.ticket_service import TicketService

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
def get_ticket_code_service() -> TicketCodeService:
    return TicketCodeService()


@lru_cache
def get_payment_gateway() -> FakePaymentGateway:
    return FakePaymentGateway()


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

@lru_cache
def get_venue_service() -> VenueService:
    return VenueService(uow_factory=SqlAlchemyUnitOfWork)


@lru_cache
def get_hold_service() -> HoldService:
    settings = get_settings()
    return HoldService(
        uow_factory=SqlAlchemyUnitOfWork,
        clock=get_clock(),
        hold_ttl_minutes=settings.hold_ttl_minutes,
        max_seats_per_user=settings.max_seats_per_user_per_event,
    )


@lru_cache
def get_order_service() -> OrderService:
    return OrderService(uow_factory=SqlAlchemyUnitOfWork, clock=get_clock())


@lru_cache
def get_payment_service() -> PaymentService:
    return PaymentService(
        uow_factory=SqlAlchemyUnitOfWork,
        clock=get_clock(),
        gateway=get_payment_gateway(),
        code_gen=get_ticket_code_service(),
    )


@lru_cache
def get_ticket_service() -> TicketService:
    return TicketService(uow_factory=SqlAlchemyUnitOfWork, clock=get_clock())


@lru_cache
def get_event_service() -> EventService:
    return EventService(uow_factory=SqlAlchemyUnitOfWork, clock=get_clock())


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
VenueServiceDep = Annotated[VenueService, Depends(get_venue_service)]
HoldServiceDep = Annotated[HoldService, Depends(get_hold_service)]
OrderServiceDep = Annotated[OrderService, Depends(get_order_service)]
PaymentServiceDep = Annotated[PaymentService, Depends(get_payment_service)]
TicketServiceDep = Annotated[TicketService, Depends(get_ticket_service)]
EventServiceDep = Annotated[EventService, Depends(get_event_service)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
