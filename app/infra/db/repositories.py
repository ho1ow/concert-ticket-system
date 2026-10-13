"""Repository implementations. Chỉ tầng này biết đến SQLAlchemy.

Mỗi repository dịch qua lại giữa ORM model và dataclass của ``app.domain``,
nên tầng services không cầm đối tượng ORM.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.entities import RefreshToken, User
from app.domain.errors import EmailExists
from app.infra.db.models import RefreshTokenModel, UserModel


def _to_user(row: UserModel) -> User:
    return User(
        id=row.id,
        email=row.email,
        password_hash=row.password_hash,
        role=row.role,
        is_active=row.is_active,
        failed_logins=row.failed_logins,
        locked_until=row.locked_until,
        created_at=row.created_at,
    )


def _to_refresh_token(row: RefreshTokenModel) -> RefreshToken:
    return RefreshToken(
        id=row.id,
        user_id=row.user_id,
        token_hash=row.token_hash,
        family_id=row.family_id,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        replaced_by=row.replaced_by,
        created_at=row.created_at,
    )


class SqlUserRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, user_id: int) -> User | None:
        row = self._s.get(UserModel, user_id)
        return _to_user(row) if row else None

    def get_by_email(self, email: str) -> User | None:
        row = self._s.scalar(select(UserModel).where(UserModel.email == email))
        return _to_user(row) if row else None

    def add(self, user: User) -> User:
        row = UserModel(
            email=user.email,
            password_hash=user.password_hash,
            role=user.role,
            is_active=user.is_active,
            failed_logins=user.failed_logins,
            locked_until=user.locked_until,
        )
        try:
            # Savepoint: dịch IntegrityError thành lỗi nghiệp vụ mà không
            # phá transaction đang mở.
            with self._s.begin_nested():
                self._s.add(row)
                self._s.flush()
        except IntegrityError as exc:
            raise EmailExists("Email already registered") from exc
        return _to_user(row)

    def update(self, user: User) -> None:
        assert user.id is not None
        self._s.execute(
            update(UserModel)
            .where(UserModel.id == user.id)
            .values(
                role=user.role,
                is_active=user.is_active,
                failed_logins=user.failed_logins,
                locked_until=user.locked_until,
                password_hash=user.password_hash,
            )
        )


class SqlRefreshTokenRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, token: RefreshToken) -> RefreshToken:
        row = RefreshTokenModel(
            user_id=token.user_id,
            token_hash=token.token_hash,
            family_id=token.family_id,
            expires_at=token.expires_at,
        )
        self._s.add(row)
        self._s.flush()
        return _to_refresh_token(row)

    def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        row = self._s.scalar(
            select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash)
        )
        return _to_refresh_token(row) if row else None

    def revoke(
        self, token_id: int, *, now: datetime, replaced_by: int | None = None
    ) -> bool:
        """UPDATE có điều kiện. Cùng kỹ thuật dùng cho việc giữ ghế."""
        result = self._s.execute(
            update(RefreshTokenModel)
            .where(
                RefreshTokenModel.id == token_id,
                RefreshTokenModel.revoked_at.is_(None),
            )
            .values(revoked_at=now, replaced_by=replaced_by)
        )
        return result.rowcount == 1

    def revoke_family(self, family_id: str, *, now: datetime) -> int:
        result = self._s.execute(
            update(RefreshTokenModel)
            .where(
                RefreshTokenModel.family_id == family_id,
                RefreshTokenModel.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        return result.rowcount
