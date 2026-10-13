"""Use case xác thực: register, login, refresh.

Chỉ phụ thuộc các Protocol trong ``app.domain.ports``, không import
FastAPI, SQLAlchemy, PyJWT hay pwdlib.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import timedelta

from app.domain.auth import Actor, Role, TokenPair
from app.domain.entities import RefreshToken, User
from app.domain.errors import (
    EmailExists,
    InvalidCredentials,
    InvalidRefreshToken,
    NotFound,
)
from app.domain.ports import (
    Clock,
    PasswordHasher,
    TokenIssuer,
    UnitOfWork,
)


def normalize_email(email: str) -> str:
    return email.strip().lower()


class AuthService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        hasher: PasswordHasher,
        tokens: TokenIssuer,
        clock: Clock,
        *,
        refresh_ttl_days: int = 7,
        lock_threshold: int = 5,
        lock_minutes: int = 15,
    ) -> None:
        self._uow = uow_factory
        self._hasher = hasher
        self._tokens = tokens
        self._clock = clock
        self._refresh_ttl = timedelta(days=refresh_ttl_days)
        self._lock_threshold = lock_threshold
        self._lock_duration = timedelta(minutes=lock_minutes)

    # ------------------------------------------------------------------ register
    def register(self, email: str, password: str) -> User:
        """Role luôn là USER. Schema từ chối field ``role`` trong body, nên
        không thể mass-assign quyền ADMIN."""
        user = User(
            id=None,
            email=normalize_email(email),
            password_hash=self._hasher.hash(password),
            role=Role.USER,
        )
        with self._uow() as uow:
            created = uow.users.add(user)  # UNIQUE(email) -> EmailExists
            uow.commit()
            return created

    # --------------------------------------------------------------------- login
    def login(self, email: str, password: str) -> TokenPair:
        now = self._clock.now()
        with self._uow() as uow:
            user = uow.users.get_by_email(normalize_email(email))

            # Không có user: vẫn chạy verify với hash giả để thời gian phản hồi
            # bằng trường hợp có user.
            if user is None:
                self._hasher.dummy_verify(password)
                raise InvalidCredentials("Invalid email or password")

            # Tài khoản bị khoá hoặc bị vô hiệu: cùng một thông báo, không
            # tiết lộ trạng thái tài khoản.
            if not user.is_active or user.is_locked(now):
                self._hasher.dummy_verify(password)
                raise InvalidCredentials("Invalid email or password")

            if not self._hasher.verify(password, user.password_hash):
                user.failed_logins += 1
                if user.failed_logins >= self._lock_threshold:
                    user.locked_until = now + self._lock_duration
                    user.failed_logins = 0
                uow.users.update(user)
                uow.commit()
                raise InvalidCredentials("Invalid email or password")

            user.failed_logins = 0
            user.locked_until = None
            uow.users.update(user)

            assert user.id is not None
            pair, _ = self._issue_pair(
                uow, user_id=user.id, role=user.role, family_id=str(uuid.uuid4())
            )
            uow.commit()
            return pair

    # ------------------------------------------------------------------- refresh
    def refresh(self, raw_refresh_token: str) -> TokenPair:
        """Xoay vòng refresh token kèm phát hiện tái sử dụng.

        Token đã dùng bị thu hồi ngay. Nếu nó được dùng lại (token bị đánh
        cắp), toàn bộ family bị thu hồi và phiên đăng nhập kết thúc.
        """
        now = self._clock.now()
        token_hash = self._tokens.hash_refresh_token(raw_refresh_token)

        with self._uow() as uow:
            stored = uow.refresh_tokens.get_by_hash(token_hash)
            if stored is None or stored.is_expired(now):
                raise InvalidRefreshToken("Invalid or expired refresh token")

            if stored.is_revoked:
                # Token đã thu hồi mà vẫn được dùng: huỷ cả family, commit rồi raise.
                uow.refresh_tokens.revoke_family(stored.family_id, now=now)
                uow.commit()
                raise InvalidRefreshToken("Refresh token reuse detected")

            user = uow.users.get(stored.user_id)
            if user is None or not user.is_active:
                raise InvalidRefreshToken("Invalid or expired refresh token")

            pair, new_token_id = self._issue_pair(
                uow, user_id=user.id, role=user.role, family_id=stored.family_id
            )

            # UPDATE có điều kiện: hai request refresh song song không thể
            # cùng thắng. Nếu mất, rollback cả refresh token vừa tạo.
            assert stored.id is not None
            won = uow.refresh_tokens.revoke(
                stored.id, now=now, replaced_by=new_token_id
            )
            if not won:
                uow.rollback()
                raise InvalidRefreshToken("Refresh token already used")

            uow.commit()
            return pair

    # ------------------------------------------------------------------------ me
    def me(self, actor: Actor) -> User:
        with self._uow() as uow:
            user = uow.users.get(actor.id)
            if user is None or not user.is_active:
                raise NotFound("User not found")
            return user

    # -------------------------------------------------------------- bootstrap
    def create_user(self, email: str, password: str, role: Role) -> User:
        """Tạo tài khoản với role chỉ định. Chỉ gọi từ script CLI, không có
        endpoint nào dùng hàm này."""
        user = User(
            id=None,
            email=normalize_email(email),
            password_hash=self._hasher.hash(password),
            role=role,
        )
        with self._uow() as uow:
            try:
                created = uow.users.add(user)
            except EmailExists:
                uow.rollback()
                raise
            uow.commit()
            return created

    # -------------------------------------------------------------- internals
    def _issue_pair(
        self, uow: UnitOfWork, *, user_id: int, role: Role, family_id: str
    ) -> tuple[TokenPair, int | None]:
        """Phát access token và refresh token mới.

        Id của refresh token vừa tạo được trả về thay vì cất vào ``self``, vì
        một instance service phục vụ nhiều request đồng thời.
        """
        access = self._tokens.issue_access(Actor(id=user_id, role=role))
        raw, hashed = self._tokens.new_refresh_token()
        stored = uow.refresh_tokens.add(
            RefreshToken(
                id=None,
                user_id=user_id,
                token_hash=hashed,
                family_id=family_id,
                expires_at=self._clock.now() + self._refresh_ttl,
            )
        )
        return (
            TokenPair(
                access_token=access.token,
                refresh_token=raw,
                expires_in=access.expires_in,
            ),
            stored.id,
        )
