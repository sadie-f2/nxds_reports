import csv
from datetime import date
from unittest.mock import patch

import pytest

from report_arrears import build_rows, compute_days_overdue, parse_due_date, write_csv


class TestParseDueDate:
    def test_valid_iso_string(self):
        result = parse_due_date("2025-11-15T00:00:00")
        assert result == date(2025, 11, 15)

    def test_none_returns_none(self):
        assert parse_due_date(None) is None

    def test_empty_string_returns_none(self):
        assert parse_due_date("") is None

    def test_invalid_string_returns_none(self):
        assert parse_due_date("not-a-date") is None

    def test_utc_z_suffix(self):
        result = parse_due_date("2026-01-10T00:00:00Z")
        assert result == date(2026, 1, 10)


class TestComputeDaysOverdue:
    def test_past_date_returns_positive(self):
        with patch("report_arrears.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 22)
            result = compute_days_overdue(date(2026, 1, 1))
        assert result == 52

    def test_future_date_returns_zero(self):
        with patch("report_arrears.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 22)
            result = compute_days_overdue(date(2026, 3, 1))
        assert result == 0

    def test_none_returns_zero(self):
        assert compute_days_overdue(None) == 0


class TestBuildRows:
    def test_all_fields_present(self):
        records = [
            {
                "Id": 3001,
                "CoworkerFullName": "Alice Nguyen",
                "CoworkerEmail": "alice@example.com",
                "InvoiceNumber": "INV-001",
                "TotalAmount": 150.00,
                "DueDate": "2025-11-15T00:00:00",
            }
        ]
        with patch("report_arrears.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 22)
            rows = build_rows(records)
        assert len(rows) == 1
        expected_keys = {"Id", "CoworkerFullName", "CoworkerEmail", "InvoiceNumber", "TotalAmount", "DueDate", "DaysOverdue"}
        assert set(rows[0].keys()) == expected_keys

    def test_days_overdue_computed(self):
        records = [
            {
                "Id": 1,
                "CoworkerFullName": "",
                "CoworkerEmail": "",
                "InvoiceNumber": "",
                "TotalAmount": 0,
                "DueDate": "2026-01-01T00:00:00",
            }
        ]
        with patch("report_arrears.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 22)
            rows = build_rows(records)
        assert rows[0]["DaysOverdue"] == 52

    def test_empty_records(self):
        assert build_rows([]) == []


class TestSorting:
    ROWS = [
        {"Id": 1, "CoworkerFullName": "A", "CoworkerEmail": "", "InvoiceNumber": "", "TotalAmount": 100, "DueDate": "", "DaysOverdue": 10},
        {"Id": 2, "CoworkerFullName": "B", "CoworkerEmail": "", "InvoiceNumber": "", "TotalAmount": 500, "DueDate": "", "DaysOverdue": 5},
        {"Id": 3, "CoworkerFullName": "C", "CoworkerEmail": "", "InvoiceNumber": "", "TotalAmount": 200, "DueDate": "", "DaysOverdue": 30},
    ]

    def test_sort_by_age(self):
        rows = list(self.ROWS)
        rows.sort(key=lambda r: r["DaysOverdue"], reverse=True)
        assert rows[0]["Id"] == 3  # 30 days overdue
        assert rows[1]["Id"] == 1  # 10 days overdue
        assert rows[2]["Id"] == 2  # 5 days overdue

    def test_sort_by_value(self):
        rows = list(self.ROWS)
        rows.sort(key=lambda r: r["TotalAmount"], reverse=True)
        assert rows[0]["Id"] == 2  # 500
        assert rows[1]["Id"] == 3  # 200
        assert rows[2]["Id"] == 1  # 100


class TestWriteCsv:
    def test_writes_to_file(self, tmp_path):
        rows = [
            {
                "Id": 3001,
                "CoworkerFullName": "Alice",
                "CoworkerEmail": "alice@example.com",
                "InvoiceNumber": "INV-001",
                "TotalAmount": 150.0,
                "DueDate": "2025-11-15T00:00:00",
                "DaysOverdue": 99,
            }
        ]
        out_file = tmp_path / "arrears.csv"
        write_csv(rows, str(out_file))
        content = out_file.read_text()
        assert "Id,CoworkerFullName,CoworkerEmail,InvoiceNumber,TotalAmount,DueDate,DaysOverdue" in content
        assert "Alice" in content
        assert "99" in content

    def test_writes_to_stdout(self, capsys):
        rows = [
            {
                "Id": 3001,
                "CoworkerFullName": "Bob",
                "CoworkerEmail": "bob@example.com",
                "InvoiceNumber": "INV-002",
                "TotalAmount": 350.0,
                "DueDate": "2026-01-10T00:00:00",
                "DaysOverdue": 43,
            }
        ]
        write_csv(rows)
        captured = capsys.readouterr()
        assert "DaysOverdue" in captured.out
        assert "Bob" in captured.out
