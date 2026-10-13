"""Hash mật khẩu, ký và verify JWT, sinh token ngẫu nhiên.

Chỉ tầng này import pwdlib và PyJWT. Tầng services làm việc qua Protocol
``PasswordHasher`` và ``TokenIssuer``.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

import jwt
from pwdlib import PasswordHash

from app.domain.auth import AccessToken, Actor, Role
from app.domain.errors import Unauthorized


class Argon2Hasher:
    """Hash argon2 qua pwdlib."""

    # Mật khẩu giả để verify khi không tìm thấy user, giữ thời gian phản hồi
    # không đổi, chống dò email qua timing.
    _DUMMY_PASSWORD = "timing-equalisation-placeholder"

    def __init__(self) -> None:
        self._ph = PasswordHash.recommended()
        self._dummy_hash = self._ph.hash(self._DUMMY_PASSWORD)

    def hash(self, password: str) -> str:
        return self._ph.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        try:
            return self._ph.verify(password, password_hash)
        except Exception:
            # Hash sai định dạng / hỏng dữ liệu: coi như sai mật khẩu.
            return False

    def dummy_verify(self, password: str) -> None:
        self.verify(password, self._dummy_hash)


class JwtTokenIssuer:
    """Access token JWT HS256, refresh token là chuỗi ngẫu nhiên 256-bit.

    Refresh token không phải JWT. Server lưu SHA-256 của nó để thu hồi được,
    còn access token thì stateless và tự hết hạn.
    """

    ALGORITHM = "HS256"

    def __init__(self, secret: str, issuer: str, access_ttl_seconds: int = 900) -> None:
        self._secret = secret
        self._issuer = issuer
        self._ttl = access_ttl_seconds

    def issue_access(self, actor: Actor) -> AccessToken:
        now = int(time.time())
        payload = {
            "sub": str(actor.id),
            "role": actor.role.value,
            "typ": "access",
            "iat": now,
            "exp": now + self._ttl,
            "iss": self._issuer,
            "jti": secrets.token_urlsafe(12),
        }
        # Không đưa email hay thông tin cá nhân vào payload: JWT chỉ là
        # base64, ai cũng đọc được.
        token = jwt.encode(payload, self._secret, algorithm=self.ALGORITHM)
        return AccessToken(token=token, expires_in=self._ttl)

    def decode_access(self, token: str) -> Actor:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self.ALGORITHM],  # cố định: chặn alg=none và confusion
                issuer=self._issuer,
                options={"require": ["exp", "sub", "typ", "iss"]},
            )
        except jwt.PyJWTError as exc:
            raise Unauthorized("Invalid or expired token") from exc

        if payload.get("typ") != "access":
            raise Unauthorized("Wrong token type")

        try:
            role = Role(payload["role"])
            user_id = int(payload["sub"])
        except (KeyError, ValueError) as exc:
            raise Unauthorized("Malformed token claims") from exc

        return Actor(id=user_id, role=role)

    def new_refresh_token(self) -> tuple[str, str]:
        raw = secrets.token_urlsafe(32)  # 256-bit entropy
        return raw, self.hash_refresh_token(raw)

    def hash_refresh_token(self, raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()


def new_ticket_code() -> str:
    """Mã QR của vé phải ngẫu nhiên, không đoán được từ id tăng dần."""
    return secrets.token_urlsafe(16)


def verify_webhook_signature(
    body: bytes, timestamp: str, signature: str, *, secret: str, max_skew: int = 300
) -> None:
    """Xác thực webhook giữa hai máy, không dùng JWT.

    Phải gọi trên raw body, trước khi parse JSON.
    """
    try:
        skew = abs(time.time() - int(timestamp))
    except (TypeError, ValueError) as exc:
        raise Unauthorized("Bad timestamp") from exc
    if skew > max_skew:
        raise Unauthorized("Stale webhook")

    expected = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):  # so sánh thời gian hằng
        raise Unauthorized("Bad signature")


class SystemClock:
    """Nguồn thời gian cho tầng services (UTC).

    Các bất biến về ghế và hold vẫn phải dùng ``now()`` của database, không
    dùng giờ của worker. Xem docs/details.md §3.2.
    """

    def now(self):
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)
