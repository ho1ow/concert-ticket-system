from datetime import datetime, timedelta, timezone

import pytest

from app.domain.entities import Event, EventStatus
from app.domain.errors import InvalidState, NotFound
from app.services.event_service import EventService


class FixedClock:
    def now(self) -> datetime:
        return datetime(2030, 1, 1, tzinfo=timezone.utc)


class FakeEvents:
    def __init__(self, event: Event | None) -> None:
        self.event = event
        self.updated: Event | None = None

    def get_for_update(self, event_id: int) -> Event | None:
        if self.event is not None and self.event.id == event_id:
            return self.event
        return None

    def update(self, event: Event) -> None:
        self.updated = event


class FakeVenues:
    def __init__(self, venue_ids: set[int]) -> None:
        self.venue_ids = venue_ids

    def get(self, venue_id: int) -> object | None:
        return object() if venue_id in self.venue_ids else None


class FakeUnitOfWork:
    def __init__(self, event: Event | None, venue_ids: set[int]) -> None:
        self.events = FakeEvents(event)
        self.venues = FakeVenues(venue_ids)
        self.committed = False

    def __enter__(self) -> FakeUnitOfWork:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def commit(self) -> None:
        self.committed = True


def make_event(status: EventStatus = EventStatus.DRAFT) -> Event:
    return Event(
        id=7,
        venue_id=1,
        title="Concert",
        description="Details",
        start_time=datetime(2030, 3, 1, tzinfo=timezone.utc),
        sale_open_at=datetime(2030, 2, 1, tzinfo=timezone.utc),
        status=status,
    )


def make_service(event: Event | None, venue_ids: set[int]) -> tuple[EventService, FakeUnitOfWork]:
    uow = FakeUnitOfWork(event, venue_ids)
    return EventService(uow_factory=lambda: uow, clock=FixedClock()), uow


def test_null_values_do_not_update_event() -> None:
    event = make_event()
    service, uow = make_service(event, {1})

    result = service.update_event(
        7,
        title=None,
        description=None,
        start_time=None,
        sale_open_at=None,
        venue_id=None,
    )

    assert result is event
    assert event.title == "Concert"
    assert event.description == "Details"
    assert event.venue_id == 1
    assert uow.events.updated is None
    assert not uow.committed


def test_draft_event_updates_non_null_fields() -> None:
    event = make_event()
    service, uow = make_service(event, {1, 2})
    next_sale_open_at = datetime(2030, 2, 10, tzinfo=timezone.utc)
    next_start_time = next_sale_open_at + timedelta(days=20)

    result = service.update_event(
        7,
        title="New title",
        description=None,
        start_time=next_start_time,
        sale_open_at=next_sale_open_at,
        venue_id=2,
    )

    assert result.title == "New title"
    assert result.description == "Details"
    assert result.venue_id == 2
    assert result.start_time == next_start_time
    assert result.sale_open_at == next_sale_open_at
    assert uow.events.updated is event
    assert uow.committed


def test_published_event_allows_only_title_and_description() -> None:
    event = make_event(EventStatus.PUBLISHED)
    service, uow = make_service(event, {1})

    result = service.update_event(7, title="New title", description="New details")

    assert result.title == "New title"
    assert result.description == "New details"
    assert uow.events.updated is event
    assert uow.committed


def test_published_event_rejects_schedule_changes() -> None:
    event = make_event(EventStatus.PUBLISHED)
    service, uow = make_service(event, {1})

    with pytest.raises(InvalidState):
        service.update_event(
            7,
            start_time=datetime(2030, 4, 1, tzinfo=timezone.utc),
        )

    assert uow.events.updated is None
    assert not uow.committed


def test_missing_event_and_venue_raise_existing_not_found_error() -> None:
    service, _ = make_service(None, set())
    with pytest.raises(NotFound):
        service.update_event(404, title="New title")

    service, _ = make_service(make_event(), {1})
    with pytest.raises(NotFound):
        service.update_event(7, venue_id=404)


def test_invalid_schedule_raises_existing_invalid_state_error() -> None:
    service, uow = make_service(make_event(), {1})

    with pytest.raises(InvalidState):
        service.update_event(
            7,
            sale_open_at=datetime(2030, 3, 2, tzinfo=timezone.utc),
        )

    assert uow.events.updated is None
    assert not uow.committed
