"""
Tests for availability slot calculation logic.
Pure function — no HTTP calls, no mock patches needed.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.availability import compute_slots
from app.models import Booking

EASTERN = ZoneInfo("America/New_York")


def make_booking(from_h: int, to_h: int, resource_id: int = 10) -> Booking:
    """Create a Booking with Eastern-aware times on 2026-03-01."""
    day = datetime(2026, 3, 1, tzinfo=EASTERN)
    from_time = day + timedelta(hours=from_h)
    to_time = day + timedelta(hours=to_h)
    return Booking(
        id=1,
        resource_id=resource_id,
        resource_name="Test Resource",
        shop="Test Shop",
        member_id=1,
        member_name="Alice",
        from_time=from_time,
        to_time=to_time,
        duration_hours=to_h - from_h,
    )


def day_bounds():
    start = datetime(2026, 3, 1, 0, 0, tzinfo=EASTERN)
    end = start + timedelta(days=1)
    return start, end


class TestComputeSlotsNoBookings:
    def test_returns_24_slots_for_empty_day(self):
        start, end = day_bounds()
        slots = compute_slots([], start, end, slot_minutes=60)
        assert len(slots) == 24

    def test_slots_cover_full_day(self):
        start, end = day_bounds()
        slots = compute_slots([], start, end, slot_minutes=60)
        assert slots[0].from_time == start
        assert slots[-1].to_time == end

    def test_30_min_slots_returns_48(self):
        start, end = day_bounds()
        slots = compute_slots([], start, end, slot_minutes=30)
        assert len(slots) == 48

    def test_slots_are_contiguous(self):
        start, end = day_bounds()
        slots = compute_slots([], start, end, slot_minutes=60)
        for i in range(len(slots) - 1):
            assert slots[i].to_time == slots[i + 1].from_time


class TestComputeSlotsWithBookings:
    def test_booking_at_start_reduces_slots(self):
        start, end = day_bounds()
        bookings = [make_booking(0, 2)]  # midnight to 2am booked
        slots = compute_slots(bookings, start, end, slot_minutes=60)
        assert len(slots) == 22
        assert slots[0].from_time.hour == 2

    def test_booking_in_middle(self):
        start, end = day_bounds()
        bookings = [make_booking(10, 12)]  # 10am-noon booked
        slots = compute_slots(bookings, start, end, slot_minutes=60)
        assert len(slots) == 22
        # No slot should overlap 10-12
        for s in slots:
            assert not (s.from_time.hour >= 10 and s.to_time.hour <= 12 and s.from_time.hour < 12)

    def test_booking_at_end(self):
        start, end = day_bounds()
        bookings = [make_booking(22, 24)]  # 10pm-midnight booked
        slots = compute_slots(bookings, start, end, slot_minutes=60)
        assert len(slots) == 22

    def test_full_day_booked_returns_no_slots(self):
        start, end = day_bounds()
        bookings = [make_booking(0, 24)]
        slots = compute_slots(bookings, start, end, slot_minutes=60)
        assert slots == []

    def test_multiple_bookings(self):
        start, end = day_bounds()
        bookings = [make_booking(8, 10), make_booking(14, 16)]
        slots = compute_slots(bookings, start, end, slot_minutes=60)
        assert len(slots) == 20

    def test_adjacent_bookings(self):
        start, end = day_bounds()
        bookings = [make_booking(8, 10), make_booking(10, 12)]
        slots = compute_slots(bookings, start, end, slot_minutes=60)
        assert len(slots) == 20

    def test_different_resource_ignored(self):
        """Bookings for a different resource should be filtered upstream, not here."""
        start, end = day_bounds()
        bookings = [make_booking(8, 10, resource_id=99)]  # different resource
        # compute_slots doesn't filter by resource — caller does that
        slots = compute_slots(bookings, start, end, slot_minutes=60)
        assert len(slots) == 22  # treated as same resource

    def test_slot_boundaries_align_with_booking(self):
        start, end = day_bounds()
        bookings = [make_booking(9, 11)]
        slots = compute_slots(bookings, start, end, slot_minutes=60)
        times = [(s.from_time.hour, s.to_time.hour) for s in slots]
        assert (9, 10) not in times
        assert (10, 11) not in times
        assert (8, 9) in times
        assert (11, 12) in times
