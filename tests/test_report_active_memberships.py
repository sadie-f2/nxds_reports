import csv

import pytest

from report_active_memberships import (
    COLUMNS_FLAT,
    COLUMNS_SUMMARY,
    COLUMNS_UNIQUE,
    build_flat_rows,
    build_summary_rows,
    build_unique_rows,
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

# Alice has two contracts; Bob has one
SAMPLE_RECORDS_WITH_MULTIPLES = SAMPLE_RECORDS + [
    {
        "Id": 2005,
        "CoworkerFullName": "Alice Nguyen",
        "CoworkerEmail": "alice@example.com",
        "TariffName": "Bike Shop Storage",
        "StartDate": "2025-06-01T00:00:00",
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


class TestBuildUniqueRows:
    def test_deduplicates_by_email(self):
        rows = build_unique_rows(SAMPLE_RECORDS_WITH_MULTIPLES)
        assert len(rows) == 3  # Alice, Bob, David

    def test_correct_columns(self):
        rows = build_unique_rows(SAMPLE_RECORDS)
        for row in rows:
            assert set(row.keys()) == {"CoworkerFullName", "CoworkerEmail", "ContractCount", "Plans", "EarliestStartDate"}

    def test_single_contract_member(self):
        rows = build_unique_rows(SAMPLE_RECORDS)
        bob = next(r for r in rows if r["CoworkerEmail"] == "bob@example.com")
        assert bob["ContractCount"] == 1
        assert bob["Plans"] == "Dedicated Desk"
        assert bob["EarliestStartDate"] == "2026-01-25T00:00:00"

    def test_multiple_contracts_concatenated(self):
        rows = build_unique_rows(SAMPLE_RECORDS_WITH_MULTIPLES)
        alice = next(r for r in rows if r["CoworkerEmail"] == "alice@example.com")
        assert alice["ContractCount"] == 2
        assert "Hot Desk Monthly" in alice["Plans"]
        assert "Bike Shop Storage" in alice["Plans"]

    def test_earliest_start_date(self):
        rows = build_unique_rows(SAMPLE_RECORDS_WITH_MULTIPLES)
        alice = next(r for r in rows if r["CoworkerEmail"] == "alice@example.com")
        assert alice["EarliestStartDate"] == "2025-06-01T00:00:00"

    def test_sorted_by_name(self):
        rows = build_unique_rows(SAMPLE_RECORDS)
        names = [r["CoworkerFullName"] for r in rows]
        assert names == sorted(names)

    def test_empty_records(self):
        assert build_unique_rows([]) == []

    def test_multiples_only_excludes_singles(self):
        rows = build_unique_rows(SAMPLE_RECORDS_WITH_MULTIPLES, multiples_only=True)
        emails = [r["CoworkerEmail"] for r in rows]
        assert "alice@example.com" in emails
        assert "bob@example.com" not in emails
        assert "david@example.com" not in emails

    def test_multiples_only_count(self):
        rows = build_unique_rows(SAMPLE_RECORDS_WITH_MULTIPLES, multiples_only=True)
        assert len(rows) == 1


class TestBuildSummaryRows:
    def test_groups_by_tariff(self):
        rows = build_summary_rows(SAMPLE_RECORDS)
        tariff_names = [r["TariffName"] for r in rows]
        assert "Hot Desk Monthly" in tariff_names
        assert "Dedicated Desk" in tariff_names

    def test_sorted_descending_by_count(self):
        rows = build_summary_rows(SAMPLE_RECORDS)
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
    def test_unique_columns(self, tmp_path):
        rows = build_unique_rows(SAMPLE_RECORDS)
        out_file = tmp_path / "unique.csv"
        write_csv(rows, COLUMNS_UNIQUE, str(out_file))
        with out_file.open() as f:
            parsed = list(csv.DictReader(f))
        assert len(parsed) == 3
        assert "ContractCount" in parsed[0]
        assert "Plans" in parsed[0]

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
        rows = build_unique_rows(SAMPLE_RECORDS)
        write_csv(rows, COLUMNS_UNIQUE)
        captured = capsys.readouterr()
        assert "CoworkerFullName,CoworkerEmail,ContractCount,Plans,EarliestStartDate" in captured.out
        assert "Alice Nguyen" in captured.out
