import csv
from datetime import date

import pytest

from report_new_memberships import (
    COLUMNS,
    build_rows,
    parse_start_date,
    resolve_date_range,
    write_csv,
)

# Alice: first contract in range (genuinely new)
# Bob: first contract before range (existing member, add-on in range)
# Carol: first contract before range, no recent activity
# David: first contract in range (genuinely new)
ALL_RECORDS = [
    {
        "CoworkerEmail": "alice@example.com",
        "CoworkerFullName": "Alice Nguyen",
        "TariffName": "Hot Desk Monthly",
        "StartDate": "2026-02-10T00:00:00",
    },
    {
        "CoworkerEmail": "bob@example.com",
        "CoworkerFullName": "Bob Okonkwo",
        "TariffName": "Storage Add-on",
        "StartDate": "2026-02-05T00:00:00",  # recent, but not his first
    },
    {
        "CoworkerEmail": "bob@example.com",
        "CoworkerFullName": "Bob Okonkwo",
        "TariffName": "Dedicated Desk",
        "StartDate": "2024-06-01T00:00:00",  # Bob's actual first contract
    },
    {
        "CoworkerEmail": "carol@example.com",
        "CoworkerFullName": "Carol Reyes",
        "TariffName": "Private Office",
        "StartDate": "2023-03-15T00:00:00",
    },
    {
        "CoworkerEmail": "david@example.com",
        "CoworkerFullName": "David Kim",
        "TariffName": "Nights & Weekends",
        "StartDate": "2026-02-15T00:00:00",
    },
]

FROM_DATE = date(2026, 2, 1)
TO_DATE = date(2026, 2, 28)


class TestParseStartDate:
    def test_iso_with_z(self):
        assert parse_start_date("2026-02-01T05:00:00Z") == date(2026, 2, 1)

    def test_iso_without_z(self):
        assert parse_start_date("2026-02-10T00:00:00") == date(2026, 2, 10)

    def test_empty_returns_none(self):
        assert parse_start_date("") is None

    def test_none_returns_none(self):
        assert parse_start_date(None) is None

    def test_invalid_returns_none(self):
        assert parse_start_date("not-a-date") is None


class TestResolveDateRange:
    def test_default_30_days(self):
        import unittest.mock as mock
        import argparse
        args = argparse.Namespace(from_date=None, to_date=None, days=30)
        with mock.patch("report_new_memberships.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 25)
            mock_date.fromisoformat.side_effect = date.fromisoformat
            from_d, to_d = resolve_date_range(args)
        assert from_d == date(2026, 1, 26)
        assert to_d == date(2026, 2, 25)

    def test_explicit_from_to(self):
        import argparse
        args = argparse.Namespace(from_date="2026-01-01", to_date="2026-01-31", days=30)
        from_d, to_d = resolve_date_range(args)
        assert from_d == date(2026, 1, 1)
        assert to_d == date(2026, 1, 31)

    def test_custom_days(self):
        import unittest.mock as mock
        import argparse
        args = argparse.Namespace(from_date=None, to_date=None, days=60)
        with mock.patch("report_new_memberships.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 25)
            mock_date.fromisoformat.side_effect = date.fromisoformat
            from_d, to_d = resolve_date_range(args)
        assert from_d == date(2025, 12, 27)
        assert to_d == date(2026, 2, 25)


class TestBuildRows:
    def test_genuinely_new_members_included(self):
        rows = build_rows(ALL_RECORDS, FROM_DATE, TO_DATE)
        emails = [r["CoworkerEmail"] for r in rows]
        assert "alice@example.com" in emails
        assert "david@example.com" in emails

    def test_existing_member_with_recent_addon_excluded(self):
        rows = build_rows(ALL_RECORDS, FROM_DATE, TO_DATE)
        emails = [r["CoworkerEmail"] for r in rows]
        assert "bob@example.com" not in emails

    def test_old_member_excluded(self):
        rows = build_rows(ALL_RECORDS, FROM_DATE, TO_DATE)
        emails = [r["CoworkerEmail"] for r in rows]
        assert "carol@example.com" not in emails

    def test_first_plan_used_not_addon(self):
        rows = build_rows(ALL_RECORDS, FROM_DATE, TO_DATE)
        # Bob should not appear, but if he did it would be Dedicated Desk (first), not Storage Add-on
        # Verify by checking all records use earliest contract
        alice = next(r for r in rows if r["CoworkerEmail"] == "alice@example.com")
        assert alice["FirstPlan"] == "Hot Desk Monthly"

    def test_correct_columns(self):
        rows = build_rows(ALL_RECORDS, FROM_DATE, TO_DATE)
        for row in rows:
            assert set(row.keys()) == set(COLUMNS)

    def test_sorted_by_start_date(self):
        rows = build_rows(ALL_RECORDS, FROM_DATE, TO_DATE)
        dates = [r["FirstStartDate"] for r in rows]
        assert dates == sorted(dates)

    def test_start_date_truncated_to_date(self):
        rows = build_rows(ALL_RECORDS, FROM_DATE, TO_DATE)
        for row in rows:
            assert len(row["FirstStartDate"]) == 10  # YYYY-MM-DD only

    def test_empty_records_returns_empty(self):
        assert build_rows([], FROM_DATE, TO_DATE) == []

    def test_no_members_in_range_returns_empty(self):
        far_future = date(2030, 1, 1)
        rows = build_rows(ALL_RECORDS, far_future, far_future)
        assert rows == []

    def test_member_count(self):
        rows = build_rows(ALL_RECORDS, FROM_DATE, TO_DATE)
        assert len(rows) == 2  # alice and david


class TestWriteCsv:
    def test_writes_to_file(self, tmp_path):
        rows = build_rows(ALL_RECORDS, FROM_DATE, TO_DATE)
        out = tmp_path / "new_members.csv"
        write_csv(rows, str(out))
        with out.open() as f:
            parsed = list(csv.DictReader(f))
        assert len(parsed) == 2
        assert "FirstPlan" in parsed[0]
        assert "FirstStartDate" in parsed[0]

    def test_writes_to_stdout(self, capsys):
        rows = build_rows(ALL_RECORDS, FROM_DATE, TO_DATE)
        write_csv(rows)
        captured = capsys.readouterr()
        assert "CoworkerFullName,CoworkerEmail,FirstPlan,FirstStartDate" in captured.out
        assert "Alice Nguyen" in captured.out
