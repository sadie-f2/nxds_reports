import argparse
import csv
from datetime import date
from unittest import mock

import pytest

from report_bookings import (
    FLAT_COLUMNS,
    SUMMARY_COLUMNS,
    build_email_lookup,
    build_flat_rows,
    build_summary_rows,
    compute_duration_hours,
    extract_shop,
    resolve_date_range,
    to_eastern,
    write_csv,
)

SAMPLE_RECORDS = [
    {
        "Id": 1001,
        "BookingNumber": 101,
        "CoworkerId": 10,
        "CoworkerFullName": "Alice Member",
        "ResourceName": "DigiFab | Laser Cutter | Calico",
        "FromTime": "2026-02-01T14:00:00Z",
        "ToTime": "2026-02-01T16:00:00Z",
    },
    {
        "Id": 1002,
        "BookingNumber": 102,
        "CoworkerId": 20,
        "CoworkerFullName": "Bob Builder",
        "ResourceName": "Wood Shop",
        "FromTime": "2026-02-03T10:00:00Z",
        "ToTime": "2026-02-03T13:00:00Z",
    },
    {
        "Id": 1003,
        "BookingNumber": 103,
        "CoworkerId": 10,
        "CoworkerFullName": "Alice Member",
        "ResourceName": "Metal Shop | CNC Plasma Cutter",
        "FromTime": "2026-02-10T09:00:00Z",
        "ToTime": "2026-02-10T11:30:00Z",
    },
]

SAMPLE_MEMBERS = [
    {"CoworkerId": 10, "CoworkerEmail": "alice@example.com"},
    {"CoworkerId": 20, "CoworkerEmail": "bob@example.com"},
]


class TestResolveDateRange:
    def _args(self, days="180", from_date=None, to_date=None):
        return argparse.Namespace(days=days, from_date=from_date, to_date=to_date)

    def test_look_back(self):
        with mock.patch("report_bookings.date") as mock_date:
            mock_date.today.return_value = date(2026, 3, 1)
            mock_date.side_effect = lambda *a, **k: date(*a, **k)
            from_str, to_str = resolve_date_range(self._args(days="30"))
        assert from_str == "2026-01-30"
        assert to_str == "2026-03-01"

    def test_look_ahead(self):
        with mock.patch("report_bookings.date") as mock_date:
            mock_date.today.return_value = date(2026, 3, 1)
            mock_date.side_effect = lambda *a, **k: date(*a, **k)
            from_str, to_str = resolve_date_range(self._args(days="+14"))
        assert from_str == "2026-03-01"
        assert to_str == "2026-03-15"

    def test_explicit_from_to(self):
        args = self._args(from_date="2026-01-01", to_date="2026-01-31")
        from_str, to_str = resolve_date_range(args)
        assert from_str == "2026-01-01"
        assert to_str == "2026-01-31"


class TestExtractShop:
    def test_pipe_separator_extracts_first_part(self):
        assert extract_shop("DigiFab | Laser Cutter | Calico") == "DigiFab"

    def test_no_pipe_returns_full_name(self):
        assert extract_shop("Wood Shop") == "Wood Shop"

    def test_strips_whitespace(self):
        assert extract_shop("Metal Shop | Sandblaster") == "Metal Shop"

    def test_empty_string(self):
        assert extract_shop("") == ""


class TestToEastern:
    def test_utc_to_est(self):
        # 18:15 UTC in winter = 13:15 EST (UTC-5)
        assert to_eastern("2026-02-21T18:15:00Z") == "2026-02-21 13:15 EST"

    def test_utc_to_edt(self):
        # 18:15 UTC in summer = 14:15 EDT (UTC-4)
        assert to_eastern("2026-07-04T18:15:00Z") == "2026-07-04 14:15 EDT"

    def test_empty_returns_empty(self):
        assert to_eastern("") == ""

    def test_flat_rows_times_are_eastern(self):
        rows = build_flat_rows([{
            "Id": 1, "BookingNumber": 1, "CoworkerId": 1,
            "CoworkerFullName": "Test", "ResourceName": "Shop",
            "FromTime": "2026-02-21T18:15:00Z",
            "ToTime": "2026-02-21T20:00:00Z",
        }])
        assert rows[0]["FromTime"] == "2026-02-21 13:15 EST"
        assert rows[0]["ToTime"] == "2026-02-21 15:00 EST"


class TestComputeDurationHours:
    def test_two_hour_booking(self):
        assert compute_duration_hours("2026-02-01T14:00:00Z", "2026-02-01T16:00:00Z") == 2.0

    def test_fractional_hours(self):
        assert compute_duration_hours("2026-02-01T09:00:00Z", "2026-02-01T10:30:00Z") == 1.5

    def test_missing_from_time(self):
        assert compute_duration_hours("", "2026-02-01T16:00:00Z") == ""

    def test_missing_to_time(self):
        assert compute_duration_hours("2026-02-01T14:00:00Z", "") == ""

    def test_both_missing(self):
        assert compute_duration_hours("", "") == ""


class TestBuildEmailLookup:
    def test_maps_coworker_id_to_email(self):
        lookup = build_email_lookup(SAMPLE_MEMBERS)
        assert lookup[10] == "alice@example.com"
        assert lookup[20] == "bob@example.com"

    def test_skips_records_without_coworker_id(self):
        records = [{"CoworkerEmail": "noid@example.com"}]
        assert build_email_lookup(records) == {}

    def test_deduplicates_same_member(self):
        records = [
            {"CoworkerId": 10, "CoworkerEmail": "alice@example.com"},
            {"CoworkerId": 10, "CoworkerEmail": "alice@example.com"},
        ]
        assert len(build_email_lookup(records)) == 1

    def test_empty_records(self):
        assert build_email_lookup([]) == {}


class TestBuildFlatRows:
    def test_correct_columns(self):
        rows = build_flat_rows(SAMPLE_RECORDS)
        for row in rows:
            assert set(row.keys()) == set(FLAT_COLUMNS)

    def test_shop_extracted(self):
        rows = build_flat_rows(SAMPLE_RECORDS)
        digifab = next(r for r in rows if "Calico" in r["ResourceName"])
        assert digifab["Shop"] == "DigiFab"
        wood = next(r for r in rows if r["ResourceName"] == "Wood Shop")
        assert wood["Shop"] == "Wood Shop"

    def test_duration_computed(self):
        rows = build_flat_rows(SAMPLE_RECORDS)
        laser = next(r for r in rows if "Calico" in r["ResourceName"])
        assert laser["DurationHours"] == 2.0

    def test_email_lookup_applied(self):
        lookup = build_email_lookup(SAMPLE_MEMBERS)
        rows = build_flat_rows(SAMPLE_RECORDS, email_lookup=lookup)
        laser = next(r for r in rows if "Calico" in r["ResourceName"])
        assert laser["CoworkerEmail"] == "alice@example.com"

    def test_missing_email_lookup_gives_empty(self):
        rows = build_flat_rows(SAMPLE_RECORDS)
        for row in rows:
            assert row["CoworkerEmail"] == ""

    def test_sorted_by_shop_resource_time(self):
        rows = build_flat_rows(SAMPLE_RECORDS)
        keys = [(r["Shop"], r["ResourceName"], r["FromTime"]) for r in rows]
        assert keys == sorted(keys)

    def test_empty_records(self):
        assert build_flat_rows([]) == []


class TestBuildSummaryRows:
    def test_groups_by_resource(self):
        rows = build_summary_rows(SAMPLE_RECORDS)
        names = [r["ResourceName"] for r in rows]
        assert "DigiFab | Laser Cutter | Calico" in names
        assert "Wood Shop" in names

    def test_correct_columns(self):
        rows = build_summary_rows(SAMPLE_RECORDS)
        for row in rows:
            assert set(row.keys()) == set(SUMMARY_COLUMNS)

    def test_booking_count(self):
        rows = build_summary_rows(SAMPLE_RECORDS)
        laser = next(r for r in rows if "Calico" in r["ResourceName"])
        assert laser["BookingCount"] == 1
        assert laser["TotalHours"] == 2.0

    def test_total_hours_summed(self):
        rows = build_summary_rows(SAMPLE_RECORDS)
        wood = next(r for r in rows if r["ResourceName"] == "Wood Shop")
        assert wood["TotalHours"] == 3.0

    def test_sorted_alphabetically(self):
        rows = build_summary_rows(SAMPLE_RECORDS)
        keys = [(r["Shop"], r["ResourceName"]) for r in rows]
        assert keys == sorted(keys)

    def test_empty_records(self):
        assert build_summary_rows([]) == []


class TestWriteCsv:
    def test_flat_writes_to_file(self, tmp_path):
        rows = build_flat_rows(SAMPLE_RECORDS)
        out = tmp_path / "bookings.csv"
        write_csv(rows, FLAT_COLUMNS, str(out))
        with out.open() as f:
            parsed = list(csv.DictReader(f))
        assert len(parsed) == 3
        assert "Shop" in parsed[0]
        assert "DurationHours" in parsed[0]

    def test_summary_writes_to_file(self, tmp_path):
        rows = build_summary_rows(SAMPLE_RECORDS)
        out = tmp_path / "summary.csv"
        write_csv(rows, SUMMARY_COLUMNS, str(out))
        with out.open() as f:
            parsed = list(csv.DictReader(f))
        assert len(parsed) == 3
        assert "BookingCount" in parsed[0]

    def test_writes_to_stdout(self, capsys):
        rows = build_flat_rows(SAMPLE_RECORDS)
        write_csv(rows, FLAT_COLUMNS)
        captured = capsys.readouterr()
        assert "Shop,ResourceName" in captured.out
        assert "Wood Shop" in captured.out
