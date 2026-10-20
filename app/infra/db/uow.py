"""Unit of Work: gom các repository vào cùng một transaction."""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from app.infra.db.repositories import SqlRefreshTokenRepository, SqlUserRepository, SqlVenueRepository
from app.infra.db.session import get_session_factory


class SqlAlchemyUnitOfWork:
    """Mở session khi vào ``with``, rollback nếu có exception, luôn close.

    Không tự commit: service phải gọi ``commit()`` tường minh.
    """

    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        self._session_factory = session_factory or get_session_factory()
        self._session: Session | None = None

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        self._session = self._session_factory()
        self.users = SqlUserRepository(self._session)
        self.refresh_tokens = SqlRefreshTokenRepository(self._session)
        self.venues = SqlVenueRepository(self._session)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        assert self._session is not None
        try:
            if exc_type is not None:
                self._session.rollback()
        finally:
            self._session.close()
            self._session = None

    @property
    def session(self) -> Session:
        assert self._session is not None, "UnitOfWork chưa được mở"
        return self._session

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
