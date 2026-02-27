"""
GET  /api/bookings       — list bookings in a date range
POST /api/bookings       — create a booking
DELETE /api/bookings/{id} — cancel a booking
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query

from . import cache, nexudus
from .models import Booking, CreateBookingRequest
from .resources import _extract_shop

router = APIRouter()

EASTERN = ZoneInfo("America/New_York")
CACHE_TTL = 60  # bookings cache is short — 1 minute


def _to_eastern(iso: str) -> datetime:
    """Parse a UTC ISO string and return an Eastern-aware datetime."""
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return dt.astimezone(EASTERN)


def _duration_hours(from_iso: str, to_iso: str) -> float:
    from_dt = datetime.fromisoformat(from_iso.replace("Z", "+00:00"))
    to_dt = datetime.fromisoformat(to_iso.replace("Z", "+00:00"))
    return round((to_dt - from_dt).total_seconds() / 3600, 2)


def _cache_key(from_dt: str, to_dt: str, resource_id: Optional[int]) -> str:
    return f"bookings:{from_dt}:{to_dt}:{resource_id}"


def parse_booking(rec: dict) -> Booking:
    name = rec.get("ResourceName") or ""
    from_iso = rec.get("FromTime") or ""
    to_iso = rec.get("ToTime") or ""
    return Booking(
        id=rec["Id"],
        resource_id=rec.get("ResourceId") or 0,
        resource_name=name,
        shop=_extract_shop(name),
        member_id=rec.get("CoworkerId") or 0,
        member_name=rec.get("CoworkerFullName") or "",
        from_time=_to_eastern(from_iso) if from_iso else datetime.now(EASTERN),
        to_time=_to_eastern(to_iso) if to_iso else datetime.now(EASTERN),
        duration_hours=_duration_hours(from_iso, to_iso) if from_iso and to_iso else 0.0,
    )


@router.get("/bookings", response_model=list[Booking])
def list_bookings(
    from_dt: str = Query(
        default=None,
        alias="from",
        description="Start date YYYY-MM-DD (Eastern). Defaults to today.",
    ),
    to_dt: str = Query(
        default=None,
        alias="to",
        description="End date YYYY-MM-DD (Eastern). Defaults to 7 days from start.",
    ),
    resource_id: Optional[int] = Query(default=None),
):
    today = datetime.now(EASTERN).date()
    from_date = datetime.strptime(from_dt, "%Y-%m-%d").date() if from_dt else today
    to_date = (
        datetime.strptime(to_dt, "%Y-%m-%d").date()
        if to_dt
        else from_date + timedelta(days=7)
    )

    # Convert Eastern dates to UTC ISO for Nexudus filter
    from_utc = datetime(from_date.year, from_date.month, from_date.day, tzinfo=EASTERN).astimezone(timezone.utc).isoformat()
    to_utc = datetime(to_date.year, to_date.month, to_date.day, 23, 59, 59, tzinfo=EASTERN).astimezone(timezone.utc).isoformat()

    key = _cache_key(from_utc, to_utc, resource_id)
    cached = cache.get(key, ttl=CACHE_TTL)
    if cached is not None:
        return cached

    records = nexudus.fetch_bookings(from_utc, to_utc, resource_id)
    bookings = [parse_booking(r) for r in records]

    if resource_id is not None:
        bookings = [b for b in bookings if b.resource_id == resource_id]

    bookings.sort(key=lambda b: b.from_time)
    cache.set(key, bookings)
    return bookings


@router.post("/bookings", response_model=dict, status_code=201)
def create_booking(req: CreateBookingRequest):
    from_iso = req.from_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    to_iso = req.to_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = nexudus.post_booking(req.resource_id, req.member_id, from_iso, to_iso)
    # Invalidate bookings cache so next read reflects the new booking
    cache.clear_all()
    return {"ok": True, "id": result.get("Id")}


@router.delete("/bookings/{booking_id}", status_code=204)
def cancel_booking(booking_id: int):
    nexudus.delete_booking(booking_id)
    cache.clear_all()
