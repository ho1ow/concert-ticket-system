"""Engine và session factory.

``lock_timeout`` và ``statement_timeout`` đặt ở mức connection để một request
bị kẹt không giữ connection mãi. Xem docs/details.md §3.2.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.infra.config import Settings, get_settings
from app.infra.db.models import Base


def build_engine(settings: Settings) -> Engine:
    url = settings.database_url
    if url.startswith("sqlite"):
        # Dùng cho test nhanh, không cần Postgres.
        return create_engine(
            url, echo=settings.sql_echo, connect_args={"check_same_thread": False}
        )

    options = (
        f"-c lock_timeout={settings.db_lock_timeout_ms} "
        f"-c statement_timeout={settings.db_statement_timeout_ms}"
    )
    return create_engine(
        url,
        echo=settings.sql_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_pre_ping=True,
        connect_args={"options": options},
    )


@lru_cache
def get_engine() -> Engine:
    return build_engine(get_settings())


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(), autoflush=False, expire_on_commit=False, future=True
    )


def init_schema(engine: Engine | None = None) -> None:
    """Tạo bảng nếu chưa có.

    Pha 1 dùng ``create_all``. Nếu cần versioning thì thay bằng Alembic,
    các tầng khác không bị ảnh hưởng.
    """
    Base.metadata.create_all(engine or get_engine())
