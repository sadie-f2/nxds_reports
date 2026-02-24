import csv

import pytest

from report_active_memberships import (
    COLUMNS_FLAT,
    COLUMNS_SUMMARY,
    build_flat_rows,
    build_summary_rows,
    write_csv,
)

SAMPLE_RECORDS = [
    {
        "Id": 2001,
        "CoworkerFullName": "Alice Nguyen",
        "CoworkerEmail": "alice@example.com",
        "TariffName": "Hot Desk Monthly",
        "StartDate": "2026-02-10T00:00:00",
        "Active": True,
    },
    {
        "Id": 2002,
        "CoworkerFullName": "Bob Okonkwo",
        "CoworkerEmail": "bob@example.com",
        "TariffName": "Dedicated Desk",
        "StartDate": "2026-01-25T00:00:00",
        "Active": True,
    },
    {
        "Id": 2004,
        "CoworkerFullName": "David Kim",
        "CoworkerEmail": "david@example.com",
        "TariffName": "Hot Desk Monthly",
        "StartDate": "2026-02-15T00:00:00",
        "Active": True,
    },
]


class TestBuildFlatRows:
    def test_five_columns_extracted(self):
        rows = build_flat_rows(SAMPLE_RECORDS)
        assert len(rows) == 3
        for row in rows:
            assert set(row.keys()) == {"Id", "CoworkerFullName", "CoworkerEmail", "TariffName", "StartDate"}

    def test_correct_values(self):
        rows = build_flat_rows(SAMPLE_RECORDS)
        assert rows[0]["Id"] == 2001
        assert rows[0]["CoworkerFullName"] == "Alice Nguyen"
        assert rows[0]["TariffName"] == "Hot Desk Monthly"

    def test_empty_records(self):
        assert build_flat_rows([]) == []


class TestBuildSummaryRows:
    def test_groups_by_tariff(self):
        rows = build_summary_rows(SAMPLE_RECORDS)
        tariff_names = [r["TariffName"] for r in rows]
        assert "Hot Desk Monthly" in tariff_names
        assert "Dedicated Desk" in tariff_names

    def test_sorted_descending_by_count(self):
        rows = build_summary_rows(SAMPLE_RECORDS)
        # Hot Desk Monthly has 2, Dedicated Desk has 1
        assert rows[0]["TariffName"] == "Hot Desk Monthly"
        assert rows[0]["MemberCount"] == 2
        assert rows[1]["TariffName"] == "Dedicated Desk"
        assert rows[1]["MemberCount"] == 1

    def test_correct_summary_keys(self):
        rows = build_summary_rows(SAMPLE_RECORDS)
        for row in rows:
            assert set(row.keys()) == {"TariffName", "MemberCount"}

    def test_empty_records(self):
        assert build_summary_rows([]) == []


class TestWriteCsv:
    def test_flat_list_columns(self, tmp_path):
        rows = build_flat_rows(SAMPLE_RECORDS)
        out_file = tmp_path / "active.csv"
        write_csv(rows, COLUMNS_FLAT, str(out_file))
        with out_file.open() as f:
            parsed = list(csv.DictReader(f))
        assert len(parsed) == 3
        assert parsed[0]["CoworkerFullName"] == "Alice Nguyen"

    def test_summary_columns(self, tmp_path):
        rows = build_summary_rows(SAMPLE_RECORDS)
        out_file = tmp_path / "summary.csv"
        write_csv(rows, COLUMNS_SUMMARY, str(out_file))
        with out_file.open() as f:
            parsed = list(csv.DictReader(f))
        assert parsed[0]["TariffName"] == "Hot Desk Monthly"
        assert parsed[0]["MemberCount"] == "2"

    def test_writes_to_stdout(self, capsys):
        rows = build_flat_rows(SAMPLE_RECORDS)
        write_csv(rows, COLUMNS_FLAT)
        captured = capsys.readouterr()
        assert "Id,CoworkerFullName,CoworkerEmail,TariffName,StartDate" in captured.out
        assert "Alice Nguyen" in captured.out
