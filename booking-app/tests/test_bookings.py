"""
Tests for bookings endpoint helpers.
"""

from datetime import datetime, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.bookings import parse_booking, _duration_hours, _to_eastern, check_conflicts, create_booking
from app.models import CreateBookingRequest

EASTERN = ZoneInfo("America/New_York")


class TestToEastern:
    def test_utc_winter_converts_to_est(self):
        result = _to_eastern("2026-02-01T18:00:00Z")
        assert result.hour == 13  # EST = UTC - 5
        assert str(result.tzinfo) == "America/New_York"

    def test_utc_summer_converts_to_edt(self):
        result = _to_eastern("2026-07-01T18:00:00Z")
        assert result.hour == 14  # EDT = UTC - 4

    def test_midnight_utc(self):
        result = _to_eastern("2026-02-01T05:00:00Z")
        assert result.hour == 0  # midnight EST


class TestDurationHours:
    def test_one_hour(self):
        assert _duration_hours("2026-02-01T14:00:00Z", "2026-02-01T15:00:00Z") == 1.0

    def test_two_and_half_hours(self):
        assert _duration_hours("2026-02-01T10:00:00Z", "2026-02-01T12:30:00Z") == 2.5

    def test_thirty_minutes(self):
        assert _duration_hours("2026-02-01T10:00:00Z", "2026-02-01T10:30:00Z") == 0.5


class TestParseBooking:
    def test_basic_fields(self):
        rec = {
            "Id": 1001,
            "ResourceId": 10,
            "ResourceName": "DigiFab | Laser Cutter | Calico",
            "CoworkerId": 5,
            "CoworkerFullName": "Alice Nguyen",
            "FromTime": "2026-02-01T14:00:00Z",
            "ToTime": "2026-02-01T16:00:00Z",
        }
        b = parse_booking(rec)
        assert b.id == 1001
        assert b.resource_id == 10
        assert b.member_id == 5
        assert b.member_name == "Alice Nguyen"
        assert b.duration_hours == 2.0

    def test_shop_extracted(self):
        rec = {
            "Id": 1,
            "ResourceId": 10,
            "ResourceName": "Wood Shop | ShopBot",
            "CoworkerId": 1,
            "CoworkerFullName": "Bob",
            "FromTime": "2026-02-01T10:00:00Z",
            "ToTime": "2026-02-01T11:00:00Z",
        }
        b = parse_booking(rec)
        assert b.shop == "Wood Shop"

    def test_resource_name_no_pipe(self):
        rec = {
            "Id": 2,
            "ResourceId": 11,
            "ResourceName": "Open Face Paint Booth",
            "CoworkerId": 2,
            "CoworkerFullName": "Carol",
            "FromTime": "2026-02-01T09:00:00Z",
            "ToTime": "2026-02-01T10:30:00Z",
        }
        b = parse_booking(rec)
        assert b.shop == "Open Face Paint Booth"
        assert b.duration_hours == 1.5

    def test_from_time_in_eastern(self):
        rec = {
            "Id": 3,
            "ResourceId": 10,
            "ResourceName": "DigiFab | Laser",
            "CoworkerId": 1,
            "CoworkerFullName": "Alice",
            "FromTime": "2026-02-01T18:00:00Z",
            "ToTime": "2026-02-01T19:00:00Z",
        }
        b = parse_booking(rec)
        assert b.from_time.hour == 13  # 18:00 UTC = 13:00 EST


class TestResourceExtraction:
    def test_shop_from_pipe_name(self):
        from app.resources import _extract_shop
        assert _extract_shop("DigiFab | Laser Cutter | Calico") == "DigiFab"
        assert _extract_shop("Wood Shop | ShopBot") == "Wood Shop"
        assert _extract_shop("Metal Shop") == "Metal Shop"

    def test_shop_strips_whitespace(self):
        from app.resources import _extract_shop
        assert _extract_shop("  DigiFab  | Laser") == "DigiFab"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_request(**kwargs) -> CreateBookingRequest:
    """Build a CreateBookingRequest with sensible defaults."""
    defaults = dict(
        resource_id=10,
        member_id=1,
        member_name="Alice Member",
        from_time=datetime(2030, 6, 1, 14, 0, 0, tzinfo=timezone.utc),
        to_time=datetime(2030, 6, 1, 16, 0, 0, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return CreateBookingRequest(**defaults)


# ── Past-booking validation ───────────────────────────────────────────────────

class TestPastBookingValidation:
    def test_past_start_raises_400(self):
        """create_booking should reject a start time in the past."""
        past = datetime(2000, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        req = _make_request(
            from_time=past,
            to_time=datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        from starlette.requests import Request
        from starlette.datastructures import Headers
        # Minimal mock request with a client address
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/bookings",
            "query_string": b"",
            "headers": Headers(headers={}).raw,
            "client": ("127.0.0.1", 9999),
        }
        mock_request = Request(scope)

        with pytest.raises(HTTPException) as exc_info:
            create_booking(req, mock_request)

        assert exc_info.value.status_code == 400
        assert "past" in exc_info.value.detail.lower()

    def test_future_start_does_not_raise_past_error(self):
        """A future start time should not trigger the past-booking error.

        We mock check_conflicts to return False and nexudus.post_booking to
        return a stub so the endpoint can complete without real I/O.
        """
        future_from = datetime(2030, 6, 1, 14, 0, 0, tzinfo=timezone.utc)
        future_to = datetime(2030, 6, 1, 16, 0, 0, tzinfo=timezone.utc)
        req = _make_request(from_time=future_from, to_time=future_to)

        from starlette.requests import Request
        from starlette.datastructures import Headers
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/bookings",
            "query_string": b"",
            "headers": Headers(headers={}).raw,
            "client": ("127.0.0.1", 9999),
        }
        mock_request = Request(scope)

        with patch("app.bookings.check_conflicts", return_value=False), \
             patch("app.bookings.nexudus.post_booking", return_value={"Id": 9001}):
            # Should not raise
            result = create_booking(req, mock_request)

        assert result["ok"] is True


# ── Conflict detection ────────────────────────────────────────────────────────

class TestCheckConflicts:
    def _booking_record(self, resource_id, from_iso, to_iso):
        return {
            "Id": 5001,
            "ResourceId": resource_id,
            "ResourceName": "DigiFab | Laser Cutter | Calico",
            "CoworkerId": 99,
            "CoworkerFullName": "Other Person",
            "FromTime": from_iso,
            "ToTime": to_iso,
        }

    def test_no_existing_bookings_returns_false(self):
        with patch("app.bookings.nexudus.fetch_bookings", return_value=[]):
            result = check_conflicts(
                resource_id=10,
                from_time=datetime(2030, 6, 1, 14, 0, 0, tzinfo=timezone.utc),
                to_time=datetime(2030, 6, 1, 16, 0, 0, tzinfo=timezone.utc),
            )
        assert result is False

    def test_identical_overlap_returns_true(self):
        existing = self._booking_record(10, "2030-06-01T14:00:00Z", "2030-06-01T16:00:00Z")
        with patch("app.bookings.nexudus.fetch_bookings", return_value=[existing]):
            result = check_conflicts(
                resource_id=10,
                from_time=datetime(2030, 6, 1, 14, 0, 0, tzinfo=timezone.utc),
                to_time=datetime(2030, 6, 1, 16, 0, 0, tzinfo=timezone.utc),
            )
        assert result is True

    def test_partial_overlap_start_returns_true(self):
        # New booking 13:00–15:00, existing 14:00–16:00 → overlap
        existing = self._booking_record(10, "2030-06-01T14:00:00Z", "2030-06-01T16:00:00Z")
        with patch("app.bookings.nexudus.fetch_bookings", return_value=[existing]):
            result = check_conflicts(
                resource_id=10,
                from_time=datetime(2030, 6, 1, 13, 0, 0, tzinfo=timezone.utc),
                to_time=datetime(2030, 6, 1, 15, 0, 0, tzinfo=timezone.utc),
            )
        assert result is True

    def test_partial_overlap_end_returns_true(self):
        # New booking 15:00–17:00, existing 14:00–16:00 → overlap
        existing = self._booking_record(10, "2030-06-01T14:00:00Z", "2030-06-01T16:00:00Z")
        with patch("app.bookings.nexudus.fetch_bookings", return_value=[existing]):
            result = check_conflicts(
                resource_id=10,
                from_time=datetime(2030, 6, 1, 15, 0, 0, tzinfo=timezone.utc),
                to_time=datetime(2030, 6, 1, 17, 0, 0, tzinfo=timezone.utc),
            )
        assert result is True

    def test_adjacent_no_overlap_returns_false(self):
        # New booking ends exactly when existing starts → no overlap
        existing = self._booking_record(10, "2030-06-01T16:00:00Z", "2030-06-01T18:00:00Z")
        with patch("app.bookings.nexudus.fetch_bookings", return_value=[existing]):
            result = check_conflicts(
                resource_id=10,
                from_time=datetime(2030, 6, 1, 14, 0, 0, tzinfo=timezone.utc),
                to_time=datetime(2030, 6, 1, 16, 0, 0, tzinfo=timezone.utc),
            )
        assert result is False

    def test_different_resource_id_ignored(self):
        # Booking is for resource 11, not 10 — should not conflict
        existing = self._booking_record(11, "2030-06-01T14:00:00Z", "2030-06-01T16:00:00Z")
        with patch("app.bookings.nexudus.fetch_bookings", return_value=[existing]):
            result = check_conflicts(
                resource_id=10,
                from_time=datetime(2030, 6, 1, 14, 0, 0, tzinfo=timezone.utc),
                to_time=datetime(2030, 6, 1, 16, 0, 0, tzinfo=timezone.utc),
            )
        assert result is False

    def test_conflict_raises_409_in_create_booking(self):
        """create_booking should raise HTTP 409 when check_conflicts returns True."""
        future_from = datetime(2030, 6, 1, 14, 0, 0, tzinfo=timezone.utc)
        future_to = datetime(2030, 6, 1, 16, 0, 0, tzinfo=timezone.utc)
        req = _make_request(from_time=future_from, to_time=future_to)

        from starlette.requests import Request
        from starlette.datastructures import Headers
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/bookings",
            "query_string": b"",
            "headers": Headers(headers={}).raw,
            "client": ("127.0.0.1", 9999),
        }
        mock_request = Request(scope)

        with patch("app.bookings.check_conflicts", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                create_booking(req, mock_request)

        assert exc_info.value.status_code == 409
        assert "already booked" in exc_info.value.detail.lower()
