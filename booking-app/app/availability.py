"""
GET /api/availability — available time slots for a resource on a given date.

All shops are 24/7, so availability = 24-hour day minus existing bookings.
Slots are returned in Eastern time.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query

from . import nexudus
from .bookings import parse_booking
from .models import Slot

router = APIRouter()

EASTERN = ZoneInfo("America/New_York")
DEFAULT_SLOT_MINUTES = 60


def compute_slots(
    bookings: list,
    day_start: datetime,
    day_end: datetime,
    slot_minutes: int = DEFAULT_SLOT_MINUTES,
) -> list[Slot]:
    """
    Return available slots on a 24/7 resource given a list of existing bookings.

    bookings: list of Booking objects with from_time/to_time as Eastern-aware datetimes
    day_start/day_end: Eastern-aware datetimes (midnight to midnight)
    """
    delta = timedelta(minutes=slot_minutes)

    # Sort bookings by start time; only keep those overlapping the day
    relevant = sorted(
        [b for b in bookings if b.from_time < day_end and b.to_time > day_start],
        key=lambda b: b.from_time,
    )

    slots = []
    cursor = day_start

    for booking in relevant:
        # Fill slots in the gap before this booking
        end_of_gap = min(booking.from_time, day_end)
        while cursor + delta <= end_of_gap:
            slots.append(Slot(from_time=cursor, to_time=cursor + delta))
            cursor += delta
        # Advance cursor past this booking
        cursor = max(cursor, booking.to_time)

    # Fill remaining slots after last booking
    while cursor + delta <= day_end:
        slots.append(Slot(from_time=cursor, to_time=cursor + delta))
        cursor += delta

    return slots


@router.get("/availability", response_model=list[Slot])
def get_availability(
    resource_id: int = Query(..., description="Resource ID"),
    date: str = Query(..., description="Date in Eastern time, YYYY-MM-DD"),
    slot_minutes: int = Query(default=DEFAULT_SLOT_MINUTES, ge=15, le=480),
):
    # Build Eastern day boundaries
    parsed = datetime.strptime(date, "%Y-%m-%d")
    day_start = parsed.replace(tzinfo=EASTERN)
    day_end = day_start + timedelta(days=1)

    # Fetch bookings for this resource on this day (UTC for Nexudus filter)
    from_utc = day_start.astimezone(timezone.utc).isoformat()
    to_utc = day_end.astimezone(timezone.utc).isoformat()

    records = nexudus.fetch_bookings(from_utc, to_utc, resource_id)
    bookings = [parse_booking(r) for r in records]
    bookings = [b for b in bookings if b.resource_id == resource_id]

    return compute_slots(bookings, day_start, day_end, slot_minutes)
