import csv
from datetime import date

import pytest

from report_left_recent import (
    COLUMNS,
    build_rows,
    parse_date,
    write_csv,
)

ACTIVE_RECORDS = [
    {"CoworkerEmail": "alice@example.com", "TariffName": "24/7 Membership", "Active": True},
]

INACTIVE_RECORDS = [
    {
        "CoworkerEmail": "bob@example.com",
        "CoworkerFullName": "Bob Builder",
        "TariffName": "Nights & Weekends Membership",
        "CancellationDate": "2026-01-01T05:00:00Z",
        "Active": False,
    },
    {
        "CoworkerEmail": "carol@example.com",
        "CoworkerFullName": "Carol Welder",
        "TariffName": "24/7 Sustaining Membership",
        "CancellationDate": "2025-06-15T04:00:00Z",
        "Active": False,
    },
    # Alice is active — should be excluded even though she has an old inactive contract
    {
        "CoworkerEmail": "alice@example.com",
        "CoworkerFullName": "Alice Member",
        "TariffName": "Old Plan",
        "CancellationDate": "2024-01-01T05:00:00Z",
        "Active": False,
    },
    # Bob has two inactive contracts — only most recent should appear
    {
        "CoworkerEmail": "bob@example.com",
        "CoworkerFullName": "Bob Builder",
        "TariffName": "Old Plan",
        "CancellationDate": "2025-03-01T05:00:00Z",
        "Active": False,
    },
]


class TestParseDate:
    def test_iso_with_z(self):
        d = parse_date("2026-01-01T05:00:00Z")
        assert d == date(2026, 1, 1)

    def test_iso_without_z(self):
        d = parse_date("2025-06-15T04:00:00")
        assert d == date(2025, 6, 15)

    def test_empty_string_returns_none(self):
        assert parse_date("") is None

    def test_none_returns_none(self):
        assert parse_date(None) is None

    def test_invalid_string_returns_none(self):
        assert parse_date("not-a-date") is None


class TestBuildRows:
    def test_excludes_active_members(self):
        rows = build_rows(ACTIVE_RECORDS, INACTIVE_RECORDS)
        emails = [r["CoworkerEmail"] for r in rows]
        assert "alice@example.com" not in emails

    def test_includes_lapsed_members(self):
        rows = build_rows(ACTIVE_RECORDS, INACTIVE_RECORDS)
        emails = [r["CoworkerEmail"] for r in rows]
        assert "bob@example.com" in emails
        assert "carol@example.com" in emails

    def test_most_recent_cancellation_used(self):
        rows = build_rows(ACTIVE_RECORDS, INACTIVE_RECORDS)
        bob = next(r for r in rows if r["CoworkerEmail"] == "bob@example.com")
        assert bob["LastPlan"] == "Nights & Weekends Membership"
        assert bob["CancellationDate"] == "2026-01-01"

    def test_correct_columns(self):
        rows = build_rows(ACTIVE_RECORDS, INACTIVE_RECORDS)
        for row in rows:
            assert set(row.keys()) == set(COLUMNS)

    def test_sorted_by_days_since_cancellation(self):
        rows = build_rows(ACTIVE_RECORDS, INACTIVE_RECORDS)
        days = [r["DaysSinceCancellation"] for r in rows]
        assert days == sorted(days)

    def test_days_since_cancellation_positive(self):
        rows = build_rows(ACTIVE_RECORDS, INACTIVE_RECORDS)
        for row in rows:
            assert row["DaysSinceCancellation"] >= 0

    def test_days_filter_excludes_older(self):
        # With a 60-day filter, carol (lapsed ~250 days ago) should be excluded
        # but bob (lapsed ~55 days ago as of 2026-02-25) should be included
        # We patch date.today to get deterministic results
        import unittest.mock as mock
        with mock.patch("report_left_recent.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 25)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            rows = build_rows(ACTIVE_RECORDS, INACTIVE_RECORDS, days_filter=60)
        emails = [r["CoworkerEmail"] for r in rows]
        assert "bob@example.com" in emails
        assert "carol@example.com" not in emails

    def test_no_filter_includes_all(self):
        rows = build_rows(ACTIVE_RECORDS, INACTIVE_RECORDS)
        assert len(rows) == 2

    def test_empty_active_records(self):
        # With no active records nobody is excluded, so all 3 unique emails appear
        rows = build_rows([], INACTIVE_RECORDS)
        assert len(rows) == 3  # bob, carol, alice (deduped by email)

    def test_empty_inactive_records(self):
        rows = build_rows(ACTIVE_RECORDS, [])
        assert rows == []


class TestWriteCsv:
    def test_writes_to_file(self, tmp_path):
        rows = build_rows(ACTIVE_RECORDS, INACTIVE_RECORDS)
        out = tmp_path / "left_recent.csv"
        write_csv(rows, str(out))
        with out.open() as f:
            parsed = list(csv.DictReader(f))
        assert len(parsed) == 2
        assert "CancellationDate" in parsed[0]
        assert "DaysSinceCancellation" in parsed[0]

    def test_writes_to_stdout(self, capsys):
        rows = build_rows(ACTIVE_RECORDS, INACTIVE_RECORDS)
        write_csv(rows)
        captured = capsys.readouterr()
        assert "CoworkerFullName,CoworkerEmail" in captured.out
        assert "Bob Builder" in captured.out
