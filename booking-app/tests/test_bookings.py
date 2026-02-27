"""
Tests for bookings endpoint helpers.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.bookings import parse_booking, _duration_hours, _to_eastern

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
