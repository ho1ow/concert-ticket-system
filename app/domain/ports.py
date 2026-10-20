"""Interface mà tầng services phụ thuộc vào.

Tầng services chỉ biết các Protocol ở đây, nên test được bằng fake
implementation, không cần DB, JWT thật hay thư viện hash.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from app.domain.auth import AccessToken, Actor
from app.domain.entities import RefreshToken, User, Venue, Seat


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime:
        """Thời điểm hiện tại, luôn timezone-aware (UTC)."""
        ...


@runtime_checkable
class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...

    def dummy_verify(self, password: str) -> None:
        """Chạy một phép verify giả để thời gian phản hồi không tiết lộ
        email có tồn tại hay không (chống dò qua timing)."""
        ...


@runtime_checkable
class TokenIssuer(Protocol):
    def issue_access(self, actor: Actor) -> AccessToken: ...

    def decode_access(self, token: str) -> Actor:
        """Raise Unauthorized nếu token sai, hết hạn hoặc sai ``typ``."""
        ...

    def new_refresh_token(self) -> tuple[str, str]:
        """Trả (raw_token, token_hash). Raw chỉ gửi cho client một lần."""
        ...

    def hash_refresh_token(self, raw: str) -> str: ...


@runtime_checkable
class UserRepository(Protocol):
    def get(self, user_id: int) -> User | None: ...

    def get_by_email(self, email: str) -> User | None: ...

    def add(self, user: User) -> User:
        """Raise EmailExists nếu vi phạm UNIQUE(email)."""
        ...

    def update(self, user: User) -> None: ...


@runtime_checkable
class RefreshTokenRepository(Protocol):
    def add(self, token: RefreshToken) -> RefreshToken: ...

    def get_by_hash(self, token_hash: str) -> RefreshToken | None: ...

    def revoke(
        self, token_id: int, *, now: datetime, replaced_by: int | None = None
    ) -> bool:
        """UPDATE có điều kiện ``WHERE revoked_at IS NULL``.

        Trả False nếu token đã bị thu hồi, nên hai request refresh song song
        không thể cùng thành công.
        """
        ...

    def revoke_family(self, family_id: str, *, now: datetime) -> int:
        """Thu hồi cả family khi phát hiện tái sử dụng. Trả số dòng."""
        ...

@runtime_checkable
class VenueRepository(Protocol):
    def get(self, venue_id: int) -> Venue | None: ...

    def list(self, page: int, size: int) -> tuple[list[Venue], int]: ...

    def add(self, venue: Venue) -> Venue:
        """Raise VenueExists nếu vi phạm UNIQUE(name)."""
        ...

    def update(self, venue: Venue) -> None: ...

    def list_seats(self, venue_id: int, page: int, size: int) -> tuple[list[Seat], int]: ...

@runtime_checkable
class SeatRepository(Protocol):
    def add_many(self, seats: list[Seat]) -> int: ...

@runtime_checkable
class UnitOfWork(Protocol):
    users: UserRepository
    venues: VenueRepository
    refresh_tokens: RefreshTokenRepository
    seats: SeatRepository

    def __enter__(self) -> UnitOfWork: ...

    def __exit__(self, exc_type, exc, tb) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
