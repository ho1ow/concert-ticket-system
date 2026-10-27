"""Repository implementations. Chỉ tầng này biết đến SQLAlchemy.

Mỗi repository dịch qua lại giữa ORM model và dataclass của ``app.domain``,
nên tầng services không cầm đối tượng ORM.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.entities import (
    Event,
    EventSeat,
    EventStatus,
    EventZone,
    Hold,
    HoldStatus,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    RefreshToken,
    Seat,
    SeatStatus,
    Ticket,
    User,
    Venue,
)
from app.domain.errors import EmailExists, InvalidState
from app.infra.db.models import (
    EventModel,
    EventSeatModel,
    EventZoneModel,
    EventZoneSeatModel,
    HoldModel,
    OrderItemModel,
    OrderModel,
    PaymentModel,
    RefreshTokenModel,
    SeatModel,
    TicketModel,
    UserModel,
    VenueModel,
)


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

def _to_venue(row: VenueModel) -> Venue:
    return Venue(
        id=row.id,
        name=row.name,
        address=row.address,
        created_at=row.created_at,
    )

def _to_seat(row: SeatModel) -> Seat:
    return Seat(
        id=row.id,
        venue_id=row.venue_id,
        section=row.section,
        row=row.row,
        number=row.number,
    )

def _to_event(row: EventModel) -> Event:
    return Event(
        id=row.id,
        venue_id=row.venue_id,
        title=row.title,
        description=row.description,
        start_time=row.start_time,
        sale_open_at=row.sale_open_at,
        status=row.status,
        created_at=row.created_at,
    )


def _to_event_seat(row: EventSeatModel) -> EventSeat:
    return EventSeat(
        id=row.id,
        event_id=row.event_id,
        seat_id=row.seat_id,
        zone_id=row.zone_id,
        status=row.status,
        hold_id=row.hold_id,
        held_until=row.held_until,
    )


def _to_hold(row: HoldModel, seat_ids: list[int]) -> Hold:
    return Hold(
        id=row.id,
        user_id=row.user_id,
        event_id=row.event_id,
        expires_at=row.expires_at,
        status=row.status,
        created_at=row.created_at,
        seat_ids=seat_ids,
    )


def _to_order(row: OrderModel) -> Order:
    return Order(
        id=row.id,
        user_id=row.user_id,
        event_id=row.event_id,
        hold_id=row.hold_id,
        total=row.total,
        expires_at=row.expires_at,
        status=row.status,
        created_at=row.created_at,
    )


def _to_order_item(row: OrderItemModel) -> OrderItem:
    return OrderItem(
        id=row.id,
        order_id=row.order_id,
        event_seat_id=row.event_seat_id,
        price=row.price,
    )


def _to_payment(row: PaymentModel) -> Payment:
    return Payment(
        id=row.id,
        user_id=row.user_id,
        order_id=row.order_id,
        idempotency_key=row.idempotency_key,
        status=row.status,
        amount=row.amount,
        provider_ref=row.provider_ref,
        response=row.response,
        created_at=row.created_at,
    )


def _to_ticket(row: TicketModel) -> Ticket:
    return Ticket(
        id=row.id,
        order_id=row.order_id,
        event_seat_id=row.event_seat_id,
        code=row.code,
        checked_in_at=row.checked_in_at,
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


class SqlEventRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, event_id: int) -> Event | None:
        row = self._s.get(EventModel, event_id)
        return _to_event(row) if row else None

    def get_for_update(self, event_id: int) -> Event | None:
        row = self._s.scalar(
            select(EventModel)
            .where(EventModel.id == event_id)
            .with_for_update()
        )
        return _to_event(row) if row else None

    def add(self, event: Event) -> Event:
        row = EventModel(
            venue_id=event.venue_id,
            title=event.title,
            description=event.description,
            start_time=event.start_time,
            sale_open_at=event.sale_open_at,
            status=event.status,
        )
        self._s.add(row)
        self._s.flush()
        return _to_event(row)

    def update(self, event: Event) -> None:
        assert event.id is not None
        self._s.execute(
            update(EventModel)
            .where(EventModel.id == event.id)
            .values(
                title=event.title,
                description=event.description,
                start_time=event.start_time,
                sale_open_at=event.sale_open_at,
                status=event.status,
                venue_id=event.venue_id,
            )
        )

    def delete(self, event_id: int) -> bool:
        result = self._s.execute(
            update(EventModel)
            .where(
                EventModel.id == event_id,
                EventModel.status == EventStatus.DRAFT,
            )
            .values(status=EventStatus.CANCELLED)
        )
        return result.rowcount == 1

    def list_paginated(
        self,
        *,
        status: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int,
        size: int,
        include_drafts: bool = False,
    ) -> tuple[list[Event], int]:
        conditions = []
        if not include_drafts:
            conditions.append(EventModel.status == EventStatus.PUBLISHED)
        elif status is not None:
            conditions.append(EventModel.status == status)
        if date_from is not None:
            conditions.append(EventModel.start_time >= date_from)
        if date_to is not None:
            conditions.append(EventModel.start_time <= date_to)

        base = select(EventModel)
        if conditions:
            base = base.where(*conditions)

        total = self._s.scalar(
            select(func.count()).select_from(base.subquery())
        ) or 0

        rows = self._s.scalars(
            base.order_by(EventModel.start_time.asc(), EventModel.id.asc())
            .offset((page - 1) * size)
            .limit(size)
        ).all()

        return [_to_event(r) for r in rows], int(total)


class SqlEventSeatRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, event_seat_id: int) -> EventSeat | None:
        row = self._s.get(EventSeatModel, event_seat_id)
        return _to_event_seat(row) if row else None

    def list_by_event(
        self, event_id: int, *, zone_id: int | None = None
    ) -> list[EventSeat]:
        stmt = select(EventSeatModel).where(EventSeatModel.event_id == event_id)
        if zone_id is not None:
            stmt = stmt.where(EventSeatModel.zone_id == zone_id)
        stmt = stmt.order_by(EventSeatModel.id.asc())
        rows = self._s.scalars(stmt).all()
        return [_to_event_seat(r) for r in rows]

    def list_with_seat(
        self, *, event_id: int, zone_id: int | None = None
    ) -> list[tuple[EventSeat, Any]]:
        from app.infra.db.models import SeatModel

        stmt = (
            select(EventSeatModel, SeatModel)
            .join(SeatModel, EventSeatModel.seat_id == SeatModel.id)
            .where(EventSeatModel.event_id == event_id)
        )
        if zone_id is not None:
            stmt = stmt.where(EventSeatModel.zone_id == zone_id)
        stmt = stmt.order_by(EventSeatModel.id.asc())
        rows = self._s.execute(stmt).all()
        return [(_to_event_seat(es), s) for es, s in rows]

    def zones_with_meta(
        self, event_id: int
    ) -> dict[int, tuple[str, int]]:
        from app.infra.db.models import EventZoneModel

        rows = self._s.execute(
            select(EventZoneModel.id, EventZoneModel.name, EventZoneModel.price).where(
                EventZoneModel.event_id == event_id
            )
        ).all()
        return {int(r[0]): (str(r[1]), int(r[2])) for r in rows}

    def count_zones_seats(self, event_id: int) -> int:
        result = self._s.scalar(
            select(func.count(EventSeatModel.id)).where(
                EventSeatModel.event_id == event_id
            )
        )
        return int(result or 0)

    def list_by_hold(self, hold_id: int) -> list[EventSeat]:
        rows = self._s.scalars(
            select(EventSeatModel)
            .where(EventSeatModel.hold_id == hold_id)
            .order_by(EventSeatModel.id.asc())
        ).all()
        return [_to_event_seat(r) for r in rows]

    def lock_seats_atomically(
        self,
        *,
        event_id: int,
        seat_ids: list[int],
        hold_id: int,
        now: datetime,
        new_held_until: datetime,
    ) -> list[int]:
        ordered = sorted(set(seat_ids))
        if not ordered:
            return []
        stmt = (
            update(EventSeatModel)
            .where(
                EventSeatModel.event_id == event_id,
                EventSeatModel.id.in_(ordered),
            )
            .where(
                (EventSeatModel.status == SeatStatus.AVAILABLE)
                | (
                    (EventSeatModel.status == SeatStatus.HELD)
                    & (EventSeatModel.held_until.is_(None))
                )
                | (
                    (EventSeatModel.status == SeatStatus.HELD)
                    & (EventSeatModel.held_until <= now)
                )
            )
            .values(
                status=SeatStatus.HELD,
                hold_id=hold_id,
                held_until=new_held_until,
            )
            .returning(EventSeatModel.id)
        )
        rows = self._s.execute(stmt).scalars().all()
        return [int(r) for r in rows]

    def release_held_by_hold(
        self, *, hold_id: int, now: datetime
    ) -> int:
        result = self._s.execute(
            update(EventSeatModel)
            .where(
                EventSeatModel.hold_id == hold_id,
                EventSeatModel.status == SeatStatus.HELD,
            )
            .values(
                status=SeatStatus.AVAILABLE,
                hold_id=None,
                held_until=None,
            )
        )
        return result.rowcount or 0

    def mark_sold_by_hold(
        self, *, hold_id: int, now: datetime
    ) -> list[int]:
        stmt = (
            update(EventSeatModel)
            .where(
                EventSeatModel.hold_id == hold_id,
                EventSeatModel.status == SeatStatus.HELD,
                EventSeatModel.held_until >= now,
            )
            .values(status=SeatStatus.SOLD, hold_id=None, held_until=None)
            .returning(EventSeatModel.id)
        )
        rows = self._s.execute(stmt).scalars().all()
        return [int(r) for r in rows]

    def add_many(self, items: list[EventSeat]) -> None:
        if not items:
            return
        self._s.add_all(
            [
                EventSeatModel(
                    event_id=i.event_id,
                    seat_id=i.seat_id,
                    zone_id=i.zone_id,
                    status=i.status,
                )
                for i in items
            ]
        )
        self._s.flush()


class SqlEventZoneRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, zone_id: int) -> EventZoneModel | None:
        return self._s.get(EventZoneModel, zone_id)

    def prices_for_event(self, event_id: int, zone_ids: list[int]) -> dict[int, int]:
        if not zone_ids:
            return {}
        rows = self._s.execute(
            select(EventZoneModel.id, EventZoneModel.price).where(
                EventZoneModel.event_id == event_id,
                EventZoneModel.id.in_(zone_ids),
            )
        ).all()
        return {int(r[0]): int(r[1]) for r in rows}

    def list_by_event(self, event_id: int) -> list[EventZoneModel]:
        rows = self._s.scalars(
            select(EventZoneModel)
            .where(EventZoneModel.event_id == event_id)
            .order_by(EventZoneModel.id.asc())
        ).all()
        return list(rows)

    def add(self, zone: EventZone) -> EventZone:
        row = EventZoneModel(
            event_id=zone.event_id,
            name=zone.name,
            price=zone.price,
        )

        self._s.add(row)
        self._s.flush()

        return EventZone(
            id=row.id,
            event_id=row.event_id,
            name=row.name,
            price=row.price,
        )

    def assigned_seat_ids(
        self, event_id: int, seat_ids: list[int]
    ) -> list[int]:
        if not seat_ids:
            return []

        rows = self._s.scalars(
            select(EventZoneSeatModel.seat_id).where(
                EventZoneSeatModel.event_id == event_id,
                EventZoneSeatModel.seat_id.in_(seat_ids),
            )
        ).all()
        return [int(seat_id) for seat_id in rows]

    def assign_seats(
        self, *, event_id: int, zone_id: int, seat_ids: list[int]
    ) -> None:
        rows = [
            EventZoneSeatModel(
                event_id=event_id,
                zone_id=zone_id,
                seat_id=seat_id,
            )
            for seat_id in seat_ids
        ]

        try:
            with self._s.begin_nested():
                self._s.add_all(rows)
                self._s.flush()
        except IntegrityError as exc:
            raise InvalidState(
                "Tồn tại ghế đã được gán cho zone khác"
            ) from exc

    def seat_zone_map(self, event_id: int) -> dict[int, int]:
        rows = self._s.execute(
            select(EventZoneSeatModel.seat_id, EventZoneSeatModel.zone_id)
            .join(
                EventZoneModel,
                EventZoneModel.id == EventZoneSeatModel.zone_id,
            )
            .where(
                EventZoneSeatModel.event_id == event_id,
                EventZoneModel.event_id == event_id,
            )
        ).all()

        return {
            int(seat_id): int(zone_id)
            for seat_id, zone_id in rows
        }


class SqlHoldRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, hold: Hold, *, now: datetime) -> Hold:
        row = HoldModel(
            user_id=hold.user_id,
            event_id=hold.event_id,
            status=hold.status,
            expires_at=hold.expires_at,
        )
        self._s.add(row)
        self._s.flush()
        return _to_hold(row, [])

    def get(self, hold_id: int) -> Hold | None:
        row = self._s.get(HoldModel, hold_id)
        if row is None:
            return None
        seats = self.seat_ids_in_hold(hold_id)
        return _to_hold(row, seats)

    def seat_ids_in_hold(self, hold_id: int) -> list[int]:
        rows = self._s.scalars(
            select(EventSeatModel.id)
            .where(EventSeatModel.hold_id == hold_id)
            .order_by(EventSeatModel.id.asc())
        ).all()
        return [int(s) for s in rows]

    def list_for_user_event_active(
        self, *, user_id: int, event_id: int, now: datetime
    ) -> list[Hold]:
        rows = self._s.scalars(
            select(HoldModel)
            .where(
                HoldModel.user_id == user_id,
                HoldModel.event_id == event_id,
                HoldModel.status == HoldStatus.ACTIVE,
                HoldModel.expires_at > now,
            )
            .order_by(HoldModel.id.asc())
        ).all()
        result: list[Hold] = []
        for row in rows:
            assert row.id is not None
            seats = self.seat_ids_in_hold(row.id)
            result.append(_to_hold(row, seats))
        return result

    def mark_released(self, hold_id: int, *, now: datetime) -> bool:
        result = self._s.execute(
            update(HoldModel)
            .where(
                HoldModel.id == hold_id,
                HoldModel.status == HoldStatus.ACTIVE,
            )
            .values(status=HoldStatus.RELEASED)
        )
        return result.rowcount == 1

    def mark_converted(self, hold_id: int, *, now: datetime) -> bool:
        result = self._s.execute(
            update(HoldModel)
            .where(
                HoldModel.id == hold_id,
                HoldModel.status == HoldStatus.ACTIVE,
            )
            .values(status=HoldStatus.CONVERTED)
        )
        return result.rowcount == 1


class SqlOrderRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, order_id: int) -> Order | None:
        row = self._s.get(OrderModel, order_id)
        if row is None:
            return None
        order = _to_order(row)
        order.items = self.items_of(order_id)
        return order

    def list_for_user_paginated(
        self, *, user_id: int, page: int, size: int
    ) -> tuple[list[Order], int]:
        base = select(OrderModel).where(OrderModel.user_id == user_id)
        total = self._s.scalar(
            select(func.count()).select_from(base.subquery())
        ) or 0
        rows = self._s.scalars(
            base.order_by(OrderModel.created_at.desc(), OrderModel.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        ).all()
        orders: list[Order] = []
        for row in rows:
            assert row.id is not None
            order = _to_order(row)
            order.items = self.items_of(row.id)
            orders.append(order)
        return orders, int(total)

    def add(
        self, order: Order, items: list[OrderItem], *, now: datetime
    ) -> Order:
        row = OrderModel(
            user_id=order.user_id,
            event_id=order.event_id,
            hold_id=order.hold_id,
            total=order.total,
            status=order.status,
            expires_at=order.expires_at,
        )
        try:
            # Savepoint: dịch vi phạm UNIQUE(hold_id) thành lỗi nghiệp vụ, để
            # tầng service không phải biết đến SQLAlchemy.
            with self._s.begin_nested():
                self._s.add(row)
                self._s.flush()
        except IntegrityError as exc:
            raise InvalidState("Order already exists for this hold") from exc
        for item in items:
            self._s.add(
                OrderItemModel(
                    order_id=row.id,
                    event_seat_id=item.event_seat_id,
                    price=item.price,
                )
            )
        self._s.flush()
        return _to_order(row)

    def mark_paid(self, order_id: int, *, now: datetime) -> bool:
        result = self._s.execute(
            update(OrderModel)
            .where(
                OrderModel.id == order_id,
                OrderModel.status == OrderStatus.PENDING,
            )
            .values(status=OrderStatus.PAID)
        )
        return result.rowcount == 1

    def mark_cancelled(self, order_id: int, *, now: datetime) -> bool:
        result = self._s.execute(
            update(OrderModel)
            .where(
                OrderModel.id == order_id,
                OrderModel.status == OrderStatus.PENDING,
            )
            .values(status=OrderStatus.CANCELLED)
        )
        return result.rowcount == 1

    def mark_expired(self, order_id: int, *, now: datetime) -> bool:
        result = self._s.execute(
            update(OrderModel)
            .where(
                OrderModel.id == order_id,
                OrderModel.status == OrderStatus.PENDING,
            )
            .values(status=OrderStatus.EXPIRED)
        )
        return result.rowcount == 1

    def items_of(self, order_id: int) -> list[OrderItem]:
        rows = self._s.scalars(
            select(OrderItemModel)
            .where(OrderItemModel.order_id == order_id)
            .order_by(OrderItemModel.id.asc())
        ).all()
        return [_to_order_item(r) for r in rows]

    def order_items_by_event_seat(
        self, *, user_id: int, event_id: int
    ) -> list[OrderItem]:
        """Ghế đang bị chiếm bởi đơn của user, dùng để đếm quota 4 ghế.

        Chỉ tính đơn còn hiệu lực: đơn CANCELLED hoặc EXPIRED vẫn giữ nguyên
        các dòng order_items, nếu đếm cả thì user huỷ đơn một lần là mất quota
        vĩnh viễn.
        """
        rows = self._s.scalars(
            select(OrderItemModel)
            .join(OrderModel, OrderItemModel.order_id == OrderModel.id)
            .where(
                OrderModel.user_id == user_id,
                OrderModel.event_id == event_id,
                OrderModel.status.in_(
                    [OrderStatus.PENDING, OrderStatus.PAID]
                ),
            )
        ).all()
        return [_to_order_item(r) for r in rows]


class SqlPaymentRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get_by_idempotency(
        self, *, user_id: int, idempotency_key: str
    ) -> Payment | None:
        row = self._s.scalar(
            select(PaymentModel).where(
                PaymentModel.user_id == user_id,
                PaymentModel.idempotency_key == idempotency_key,
            )
        )
        return _to_payment(row) if row else None

    def get_by_provider_ref(self, provider_ref: str) -> Payment | None:
        """UNIQUE(provider_ref): dùng để chặn replay webhook."""
        row = self._s.scalar(
            select(PaymentModel).where(PaymentModel.provider_ref == provider_ref)
        )
        return _to_payment(row) if row else None

    def add(self, payment: Payment) -> Payment:
        row = PaymentModel(
            user_id=payment.user_id,
            order_id=payment.order_id,
            idempotency_key=payment.idempotency_key,
            status=payment.status,
            amount=payment.amount,
            provider_ref=payment.provider_ref,
            response=payment.response,
        )
        self._s.add(row)
        self._s.flush()
        return _to_payment(row)


class SqlTicketRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add_many(self, tickets: list[Ticket]) -> list[Ticket]:
        rows: list[TicketModel] = []
        for t in tickets:
            row = TicketModel(
                order_id=t.order_id,
                event_seat_id=t.event_seat_id,
                code=t.code,
            )
            self._s.add(row)
            rows.append(row)
        self._s.flush()
        return [_to_ticket(r) for r in rows]

    def list_for_user(self, *, user_id: int) -> list[Ticket]:
        rows = self._s.scalars(
            select(TicketModel)
            .join(OrderModel, TicketModel.order_id == OrderModel.id)
            .where(OrderModel.user_id == user_id)
            .order_by(TicketModel.id.asc())
        ).all()
        return [_to_ticket(r) for r in rows]

    def get_by_code(self, code: str) -> Ticket | None:
        row = self._s.scalar(
            select(TicketModel).where(TicketModel.code == code)
        )
        return _to_ticket(row) if row else None

    def list_with_details_for_user(
        self, *, user_id: int
    ) -> list[tuple[Ticket, EventModel, SeatModel]]:
        from app.infra.db.models import EventModel, SeatModel

        rows = self._s.execute(
            select(TicketModel, EventSeatModel, EventModel, SeatModel)
            .join(OrderModel, TicketModel.order_id == OrderModel.id)
            .join(EventSeatModel, TicketModel.event_seat_id == EventSeatModel.id)
            .join(EventModel, EventSeatModel.event_id == EventModel.id)
            .join(SeatModel, EventSeatModel.seat_id == SeatModel.id)
            .where(OrderModel.user_id == user_id)
            .order_by(TicketModel.id.asc())
        ).all()
        out: list[tuple[Ticket, EventModel, SeatModel]] = []
        for t, _es, ev, s in rows:
            out.append((_to_ticket(t), ev, s))
        return out

    def check_in(
        self, *, code: str, now: datetime
    ) -> Ticket | None:
        stmt = (
            update(TicketModel)
            .where(
                TicketModel.code == code,
                TicketModel.checked_in_at.is_(None),
            )
            .values(checked_in_at=now)
            .returning(TicketModel)
        )
        row = self._s.execute(stmt).scalar_one_or_none()
        return _to_ticket(row) if row else None

    def codes_for_order(self, order_id: int) -> list[str]:
        rows = self._s.execute(
            select(TicketModel.code)
            .where(TicketModel.order_id == order_id)
            .order_by(TicketModel.id.asc())
        ).all()
        return [str(r[0]) for r in rows]

    def items_for_orders(self, order_ids: list[int]) -> dict[int, dict]:
        ...


class SqlVenueRepository:
    def __init__(self, session: Session) -> None:
        self._s = session
    def list(self, page: int, size: int) -> tuple[list[Venue], int]:
        offset = (page - 1) * size

        total = self._s.scalar(
            select(func.count()).select_from(VenueModel)
        ) or 0

        rows = self._s.scalars(
            select(VenueModel)
            .order_by(VenueModel.id)
            .offset(offset)
            .limit(size)
        ).all()

        return [_to_venue(row) for row in rows], total

    def get(self, venue_id: int) -> Venue | None:
        row = self._s.get(VenueModel, venue_id)
        return _to_venue(row) if row else None

    def list_seats(self, venue_id: int, page: int, size: int) -> tuple[list[Seat], int]:
        offset = (page - 1) * size

        total = self._s.scalar(
            select(func.count()).select_from(SeatModel).where(SeatModel.venue_id == venue_id)
        ) or 0

        rows = self._s.scalars(
            select(SeatModel)
            .where(SeatModel.venue_id == venue_id)
            .order_by(SeatModel.section, SeatModel.row, SeatModel.number)
            .offset(offset)
            .limit(size)
        ).all()

        return [_to_seat(row) for row in rows], total

    def add(self, venue: Venue) -> Venue:
        row = VenueModel(
            name=venue.name,
            address=venue.address,
        )

        self._s.add(row)
        self._s.flush()
        return _to_venue(row)

class SqlSeatRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def list_by_venue(
        self, venue_id: int, page: int, size: int
    ) -> tuple[list[Seat], int]:
        offset = (page - 1) * size

        total = self._s.scalar(
            select(func.count())
            .select_from(SeatModel)
            .where(SeatModel.venue_id == venue_id)
        ) or 0

        rows = self._s.scalars(
            select(SeatModel)
            .where(SeatModel.venue_id == venue_id)
            .order_by(SeatModel.section, SeatModel.row, SeatModel.number)
            .offset(offset)
            .limit(size)
        ).all()

        return [_to_seat(row) for row in rows], total

    def add_many(self, seats: list[Seat]) -> int:
        rows = [
            SeatModel(
                venue_id=seat.venue_id,
                section=seat.section,
                row=seat.row,
                number=seat.number,
            )
            for seat in seats
        ]

        try:
            with self._s.begin_nested():
                self._s.add_all(rows)
                self._s.flush()
        except IntegrityError as exc:
            raise InvalidState("Có ghế đã tồn tại") from exc

        return len(rows)
    
    def list_by_ids(self, seat_ids: list[int]) -> list[Seat]:
        if not seat_ids:
            return []

        rows = self._s.scalars(
            select(SeatModel).where(SeatModel.id.in_(seat_ids))
        ).all()
        return [_to_seat(row) for row in rows]