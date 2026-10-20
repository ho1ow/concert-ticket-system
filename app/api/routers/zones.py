"""Khu vực và sơ đồ ghế của một event."""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentActor, EventServiceDep
from app.api.errors import NotImplementedYet, error_responses
from app.api.schemas import EventSeatOut, ZoneIn, ZoneOut
from app.infra.security import SystemClock

read_router = APIRouter(prefix="/events", tags=["zones & seats"])
write_router = APIRouter(prefix="/events", tags=["zones & seats"])


@read_router.get(
    "/{event_id}/zones",
    response_model=list[ZoneOut],
    summary="Danh sách khu vực kèm số ghế còn trống",
    responses=error_responses(404),
)
def list_zones(
    event_id: int, actor: CurrentActor, service: EventServiceDep
) -> list[ZoneOut]:
    zones = service.zones(actor, event_id)
    return [
        ZoneOut(
            id=z.zone.id,
            name=z.zone.name,
            price=z.zone.price,
            available_seats=z.available_seats,
        )
        for z in zones
    ]


@read_router.get(
    "/{event_id}/seats",
    response_model=list[EventSeatOut],
    summary="Sơ đồ ghế",
    description=(
        "Endpoint đọc chịu tải cao nhất. Lấy bằng một câu JOIN để tránh "
        "N+1. Ghế HELD đã quá `held_until` được trả về là AVAILABLE "
        "(lazy expiry)."
    ),
    responses=error_responses(404),
)
def list_event_seats(
    event_id: int,
    actor: CurrentActor,
    service: EventServiceDep,
    zone: str | None = Query(None, description="Lọc theo tên khu vực"),
) -> list[EventSeatOut]:
    zone_id: int | None = None
    if zone is not None:
        zones = service.zones(actor, event_id)
        for z in zones:
            if z.zone.name == zone:
                zone_id = z.zone.id
                break
    rows = service.list_event_seats(actor, event_id, zone_id=zone_id)
    zone_meta = service.zones_meta(event_id)
    now = SystemClock().now()
    out: list[EventSeatOut] = []
    for es, physical in rows:
        info = zone_meta.get(es.zone_id, ("", 0))
        out.append(
            EventSeatOut(
                event_seat_id=es.id,
                section=physical.section,
                row=physical.row,
                number=physical.number,
                zone=info[0],
                price=info[1],
                status=es.effective_status(now),
            )
        )
    return out


@write_router.post(
    "/{event_id}/zones",
    response_model=ZoneOut,
    status_code=status.HTTP_201_CREATED,
    summary="[Admin] Tạo khu vực, gán giá và ghế",
    description=(
        "Chỉ làm được khi event đang DRAFT. UNIQUE(event_id, seat_id) trên "
        "`event_zone_seats` bảo đảm mỗi ghế thuộc tối đa một zone."
    ),
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_zone(event_id: int, payload: ZoneIn) -> ZoneOut:
    raise NotImplementedYet("POST /events/{event_id}/zones")
