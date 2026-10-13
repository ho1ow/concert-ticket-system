"""Cấu hình đọc từ biến môi trường / .env."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Database
    database_url: str = "postgresql+psycopg://concert:concert@localhost:5432/concert"
    db_pool_size: int = 10
    db_max_overflow: int = 10
    db_pool_timeout: int = 5
    db_lock_timeout_ms: int = 2000
    db_statement_timeout_ms: int = 5000
    auto_create_schema: bool = True
    sql_echo: bool = False

    # Auth
    jwt_secret: str = "dev-secret-change-me"
    jwt_issuer: str = "concert-api"
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_days: int = 7
    login_lock_threshold: int = 5
    login_lock_minutes: int = 15

    # Business rules
    hold_ttl_minutes: int = 10
    max_seats_per_user_per_event: int = 4

    # Payment webhook
    webhook_secret: str = "dev-webhook-secret"
    webhook_max_skew_seconds: int = 300

    # Phase 2 benchmark switch
    hold_strategy: Literal["atomic", "naive"] = "atomic"


@lru_cache
def get_settings() -> Settings:
    return Settings()
