"""Unit of Work: gom các repository vào cùng một transaction."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.infra.db.repositories import (
    SqlEventRepository,
    SqlEventSeatRepository,
    SqlEventZoneRepository,
    SqlHoldRepository,
    SqlOrderRepository,
    SqlPaymentRepository,
    SqlRefreshTokenRepository,
    SqlTicketRepository,
    SqlUserRepository, SqlVenueRepository, SqlSeatRepository,
)
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
        self.seats = SqlSeatRepository(self._session)
        self.events = SqlEventRepository(self._session)
        self.event_seats = SqlEventSeatRepository(self._session)
        self.event_zones = SqlEventZoneRepository(self._session)
        self.holds = SqlHoldRepository(self._session)
        self.orders = SqlOrderRepository(self._session)
        self.payments = SqlPaymentRepository(self._session)
        self.tickets = SqlTicketRepository(self._session)
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

    def advisory_xact_lock(self, key1: int, key2: int) -> None:
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(:a, :b)"),
            {"a": int(key1), "b": int(key2)},
        )
