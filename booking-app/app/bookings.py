"""
GET  /api/bookings       — list bookings in a date range
POST /api/bookings       — create a booking
DELETE /api/bookings/{id} — cancel a booking
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request, Query

from . import cache, nexudus
from .models import Booking, CreateBookingRequest
from .resources import _extract_shop

router = APIRouter()

EASTERN = ZoneInfo("America/New_York")
CACHE_TTL = 60  # bookings cache is short — 1 minute
MAX_DURATION_HOURS = 23

# Booking audit log — one line per booking, appended to logs/bookings.log
_log_path = Path(__file__).parent.parent / "logs" / "bookings.log"
_log_path.parent.mkdir(exist_ok=True)

_booking_log = logging.getLogger("booking_audit")
_booking_log.setLevel(logging.INFO)
if not _booking_log.handlers:
    _handler = logging.FileHandler(_log_path)
    _handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    _booking_log.addHandler(_handler)


def _parse_nexudus_dt(iso: str) -> datetime:
    """Parse a Nexudus datetime string into a UTC-aware datetime.

    Nexudus returns facility-local times without a timezone marker
    (e.g. "2026-02-27T16:30:00"). Treat those as Eastern; honour an
    explicit Z suffix if present.
    """
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=EASTERN)
    return dt.astimezone(timezone.utc)


def _to_eastern(iso: str) -> datetime:
    """Parse a Nexudus datetime string and return an Eastern-aware datetime."""
    return _parse_nexudus_dt(iso).astimezone(EASTERN)


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


def check_conflicts(resource_id: int, from_time: datetime, to_time: datetime) -> bool:
    """Return True if any existing booking for resource_id overlaps [from_time, to_time).

    Overlap condition: a_start < b_end AND b_start < a_end
    """
    from_iso = from_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    to_iso = to_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    records = nexudus.fetch_bookings(from_iso, to_iso, resource_id)
    for rec in records:
        if rec.get("ResourceId") != resource_id:
            continue
        existing_from = _parse_nexudus_dt(rec["FromTime"])
        existing_to = _parse_nexudus_dt(rec["ToTime"])
        if from_time < existing_to and existing_from < to_time:
            return True
    return False


@router.post("/bookings", response_model=dict, status_code=201)
def create_booking(req: CreateBookingRequest, request: Request):
    # Duration validation
    duration = req.to_time - req.from_time
    if duration.total_seconds() <= 0:
        raise HTTPException(status_code=400, detail="End time must be after start time.")
    if duration.total_seconds() > MAX_DURATION_HOURS * 3600:
        raise HTTPException(
            status_code=400,
            detail=f"Bookings cannot exceed {MAX_DURATION_HOURS} hours.",
        )

    # Past-booking check
    if req.from_time < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Cannot book a start time in the past.")

    # Conflict check
    if check_conflicts(req.resource_id, req.from_time, req.to_time):
        raise HTTPException(
            status_code=409,
            detail="This resource is already booked for part or all of that time.",
        )

    # Determine IP (handle proxies)
    forwarded_for = request.headers.get("X-Forwarded-For")
    ip = forwarded_for.split(",")[0].strip() if forwarded_for else (request.client.host if request.client else "unknown")

    # Build on-behalf-of note
    on_behalf = (
        req.booked_by_id is not None
        and req.booked_by_id != req.member_id
    )
    if on_behalf:
        notes = f"Booked by {req.booked_by_name} on behalf of {req.member_name} | IP: {ip}"
    else:
        notes = f"IP: {ip}"

    from_iso = req.from_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    to_iso = req.to_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Subtract 2 seconds so Nexudus doesn't treat adjacent bookings as conflicting
    # (Nexudus uses non-strict boundary comparison: ToTime == FromTime → conflict)
    to_nexudus = (req.to_time - timedelta(seconds=2)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    result = nexudus.post_booking(req.resource_id, req.member_id, from_iso, to_nexudus, notes=notes)

    # Audit log
    duration_h = round(duration.total_seconds() / 3600, 2)
    if on_behalf:
        who = f"{req.booked_by_name} (id={req.booked_by_id}) on behalf of {req.member_name} (id={req.member_id})"
    else:
        who = f"{req.member_name} (id={req.member_id})"
    _booking_log.info(
        f"IP={ip} | {who} | resource_id={req.resource_id} | {from_iso} → {to_iso} | {duration_h}h | booking_id={result.get('Id')}"
    )

    cache.clear_all()
    return {"ok": True, "id": result.get("Id")}


@router.delete("/bookings/{booking_id}", status_code=204)
def cancel_booking(booking_id: int):
    nexudus.delete_booking(booking_id)
    cache.clear_all()
