"""Concert. Đọc là public (chỉ thấy PUBLISHED), ghi là ADMIN."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentActor, EventServiceDep
from app.api.errors import error_responses
from app.api.schemas import (
    EventDetailOut,
    EventIn,
    EventOut,
    EventUpdateIn,
    Page,
    PublishOut,
    ZoneOut,
)
from app.domain.entities import EventStatus

read_router = APIRouter(prefix="/events", tags=["events"])
write_router = APIRouter(prefix="/events", tags=["events"])


@read_router.get(
    "",
    response_model=Page[EventOut],
    summary="Danh sách concert",
    description="Endpoint đọc chịu tải cao. Public chỉ thấy event PUBLISHED.",
)
def list_events(
    actor: CurrentActor,
    service: EventServiceDep,
    status_filter: EventStatus | None = Query(None, alias="status"),
    date_from: datetime | None = Query(None, alias="from"),
    date_to: datetime | None = Query(None, alias="to"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> Page[EventOut]:
    if actor.role.value == "ADMIN" and status_filter is not None:
        items, total = service.list_for_admin(
            status=status_filter.value,
            date_from=date_from,
            date_to=date_to,
            page=page,
            size=size,
        )
    else:
        items, total = service.list_published(
            date_from=date_from,
            date_to=date_to,
            page=page,
            size=size,
        )
    return Page[EventOut](
        items=[EventOut.from_entity(e) for e in items],
        total=total,
        page=page,
        size=size,
    )


@read_router.get(
    "/{event_id}",
    response_model=EventDetailOut,
    summary="Chi tiết concert kèm zone và giá",
    responses=error_responses(404),
)
def get_event(
    event_id: int, actor: CurrentActor, service: EventServiceDep
) -> EventDetailOut:
    event, zones = service.get_with_zones(actor, event_id)
    out = EventDetailOut.from_entity(event).model_copy(
        update={
            "zones": [
                ZoneOut(
                    id=z.zone.id,
                    name=z.zone.name,
                    price=z.zone.price,
                    available_seats=z.available_seats,
                )
                for z in zones
            ]
        }
    )
    return out


@write_router.post(
    "",
    response_model=EventOut,
    status_code=status.HTTP_201_CREATED,
    summary="[Admin] Tạo concert (DRAFT)",
    description="Bắt buộc `start_time > sale_open_at > now`.",
    responses=error_responses(401, 403, 422),
)
def create_event(payload: EventIn, service: EventServiceDep) -> EventOut:
    event = service.create_event(
        venue_id=payload.venue_id,
        title=payload.title,
        description=payload.description,
        start_time=payload.start_time,
        sale_open_at=payload.sale_open_at,
    )

    return EventOut.from_entity(event)


@write_router.put(
    "/{event_id}",
    response_model=EventOut,
    summary="[Admin] Sửa concert",
    description=(
        "Sửa tự do khi DRAFT. Khi đã PUBLISHED chỉ còn title và description. "
        "Các trường nhận giá trị null sẽ không được cập nhật."
    ),
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_event(
    event_id: int, payload: EventUpdateIn, service: EventServiceDep
) -> EventOut:
    event = service.update_event(
        event_id,
        title=payload.title,
        description=payload.description,
        start_time=payload.start_time,
        sale_open_at=payload.sale_open_at,
        venue_id=payload.venue_id,
    )
    return EventOut.from_entity(event)


@write_router.delete(
    "/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="[Admin] Xoá concert (chỉ khi DRAFT)",
    responses=error_responses(401, 403, 404, 409),
)
def delete_event(event_id: int, service: EventServiceDep) -> Response:
    service.delete_event(event_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@write_router.post(
    "/{event_id}/publish",
    response_model=PublishOut,
    summary="[Admin] Mở bán, sinh event_seats",
    description=(
        "Điều kiện: event đang DRAFT, có ít nhất 1 zone, mọi ghế của venue đã "
        "được gán zone. Trong một transaction: sinh `event_seats` trạng thái "
        "AVAILABLE cho toàn bộ ghế, rồi chuyển event sang PUBLISHED."
    ),
    responses=error_responses(401, 403, 404, 409),
)
def publish_event(event_id: int, service: EventServiceDep) -> PublishOut:
    event, created = service.publish_event(event_id)

    assert event.id is not None
    return PublishOut(
        id=event.id,
        status=event.status,
        event_seats_created=created,
    )
