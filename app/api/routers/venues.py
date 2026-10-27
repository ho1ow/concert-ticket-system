"""Địa điểm và ghế vật lý. Đọc là public, ghi là ADMIN."""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.api.deps import VenueServiceDep
from app.api.errors import error_responses
from app.api.schemas import Page, SeatBulkIn, SeatBulkOut, SeatOut, VenueIn, VenueOut

read_router = APIRouter(prefix="/venues", tags=["venues"])
write_router = APIRouter(prefix="/venues", tags=["venues"])


@read_router.get(
    "",
    response_model=Page[VenueOut],
    summary="Danh sách địa điểm (phân trang)",
)
def list_venues(
    service: VenueServiceDep,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> Page[VenueOut]:
    venues, total = service.list_venues(page, size)

    return Page[VenueOut](
        items=[VenueOut.from_entity(v) for v in venues],
        total=total,
        page=page,
        size=size,
    )


@read_router.get(
    "/{venue_id}",
    response_model=VenueOut,
    summary="Chi tiết địa điểm",
    responses=error_responses(404),
)
def get_venue(venue_id: int, service: VenueServiceDep) -> VenueOut:
    venue = service.get_venue(venue_id)
    return VenueOut.from_entity(venue)


@read_router.get(
    "/{venue_id}/seats",
    response_model=Page[SeatOut],
    summary="Ghế vật lý của địa điểm",
    responses=error_responses(404),
)
def list_venue_seats(
    service: VenueServiceDep,
    venue_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(100, ge=1, le=100),
) -> Page[SeatOut]:
    seats, total = service.list_seats(venue_id, page, size)

    return Page[SeatOut](
        items=[SeatOut.from_entity(s) for s in seats],
        total=total,
        page=page,
        size=size, 
    )


@write_router.post(
    "",
    response_model=VenueOut,
    status_code=status.HTTP_201_CREATED,
    summary="[Admin] Tạo địa điểm",
    responses=error_responses(401, 403, 422),
)
def create_venue(payload: VenueIn, service: VenueServiceDep) -> VenueOut:
    venue = service.create_venue(payload.name, payload.address)
    return VenueOut.from_entity(venue)


@write_router.post(
    "/{venue_id}/seats",
    response_model=SeatBulkOut,
    status_code=status.HTTP_201_CREATED,
    summary="[Admin] Tạo ghế hàng loạt",
    description=(
        "Sinh ghế theo từng dải `{section, row, from, to}`. "
        "UNIQUE(venue_id, section, row, number) chặn trùng ở mức DB."
    ),
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_seats(venue_id: int, payload: SeatBulkIn, service: VenueServiceDep) -> SeatBulkOut:
    ranges = [(r.section, r.row, r.from_, r.to) for r in payload.ranges]

    created = service.create_seats(venue_id, ranges)
    return SeatBulkOut(created=created)
