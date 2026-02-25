import csv
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from report_new_contracts import build_rows, resolve_date_range, write_csv


class TestResolveDateRange:
    def test_days_default(self):
        args = MagicMock()
        args.from_date = None
        args.to_date = None
        args.days = 30
        with patch("report_new_contracts.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 22)
            from_str, to_str = resolve_date_range(args)
        assert from_str == "2026-01-23"
        assert to_str == "2026-02-22"

    def test_explicit_from_to(self):
        args = MagicMock()
        args.from_date = "2026-01-01"
        args.to_date = "2026-02-22"
        args.days = 30
        from_str, to_str = resolve_date_range(args)
        assert from_str == "2026-01-01"
        assert to_str == "2026-02-22"

    def test_custom_days(self):
        args = MagicMock()
        args.from_date = None
        args.to_date = None
        args.days = 60
        with patch("report_new_contracts.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 22)
            from_str, to_str = resolve_date_range(args)
        assert from_str == "2025-12-24"
        assert to_str == "2026-02-22"

    def test_from_only_fills_to_with_today(self):
        args = MagicMock()
        args.from_date = "2026-01-15"
        args.to_date = None
        args.days = 30
        with patch("report_new_contracts.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 22)
            from_str, to_str = resolve_date_range(args)
        assert from_str == "2026-01-15"
        assert to_str == "2026-02-22"


class TestBuildRows:
    def test_correct_field_mapping(self):
        records = [
            {
                "Id": 2001,
                "CoworkerFullName": "Alice Nguyen",
                "CoworkerEmail": "alice@example.com",
                "TariffName": "Hot Desk Monthly",
                "StartDate": "2026-02-10T00:00:00",
                "EndDate": "2026-12-31T00:00:00",
            }
        ]
        rows = build_rows(records)
        assert len(rows) == 1
        assert rows[0]["Id"] == 2001
        assert rows[0]["CoworkerFullName"] == "Alice Nguyen"
        assert rows[0]["CoworkerEmail"] == "alice@example.com"
        assert rows[0]["TariffName"] == "Hot Desk Monthly"
        assert rows[0]["StartDate"] == "2026-02-10T00:00:00"
        assert rows[0]["EndDate"] == "2026-12-31T00:00:00"

    def test_null_end_date(self):
        records = [
            {
                "Id": 2005,
                "CoworkerFullName": "Elena",
                "CoworkerEmail": "elena@example.com",
                "TariffName": "Virtual Office",
                "StartDate": "2025-06-01T00:00:00",
                "EndDate": None,
            }
        ]
        rows = build_rows(records)
        assert rows[0]["EndDate"] == ""

    def test_empty_records(self):
        assert build_rows([]) == []


class TestWriteCsv:
    def test_writes_to_file(self, tmp_path):
        rows = [
            {
                "Id": 2001,
                "CoworkerFullName": "Alice",
                "CoworkerEmail": "alice@example.com",
                "TariffName": "Hot Desk",
                "StartDate": "2026-02-10",
                "EndDate": "2026-12-31",
            }
        ]
        out_file = tmp_path / "new_memberships.csv"
        write_csv(rows, str(out_file))
        content = out_file.read_text()
        assert "Id,CoworkerFullName,CoworkerEmail,TariffName,StartDate,EndDate" in content
        assert "Alice" in content

    def test_header_and_rows_correct(self, tmp_path):
        rows = [
            {
                "Id": 1,
                "CoworkerFullName": "A",
                "CoworkerEmail": "a@x.com",
                "TariffName": "Plan A",
                "StartDate": "2026-01-01",
                "EndDate": "",
            },
            {
                "Id": 2,
                "CoworkerFullName": "B",
                "CoworkerEmail": "b@x.com",
                "TariffName": "Plan B",
                "StartDate": "2026-02-01",
                "EndDate": "2027-02-01",
            },
        ]
        out_file = tmp_path / "out.csv"
        write_csv(rows, str(out_file))
        with out_file.open() as f:
            parsed = list(csv.DictReader(f))
        assert parsed[0]["CoworkerFullName"] == "A"
        assert parsed[1]["EndDate"] == "2027-02-01"
