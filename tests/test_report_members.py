import csv

import pytest

from report_members import build_rows, extract_tariff, write_csv


class TestExtractTariff:
    def test_none_returns_empty(self):
        assert extract_tariff({"Tariff": None}) == ""

    def test_missing_key_returns_empty(self):
        assert extract_tariff({}) == ""

    def test_string_value(self):
        assert extract_tariff({"Tariff": "Dedicated Desk"}) == "Dedicated Desk"

    def test_dict_returns_name(self):
        assert extract_tariff({"Tariff": {"Id": 10, "Name": "Hot Desk Monthly"}}) == "Hot Desk Monthly"

    def test_dict_missing_name_returns_empty(self):
        assert extract_tariff({"Tariff": {"Id": 10}}) == ""


class TestBuildRows:
    def test_correct_field_mapping(self):
        records = [
            {
                "Id": 1001,
                "FullName": "Alice Nguyen",
                "Email": "alice@example.com",
                "Active": True,
                "Tariff": {"Id": 10, "Name": "Hot Desk Monthly"},
            }
        ]
        rows = build_rows(records)
        assert len(rows) == 1
        assert rows[0]["Id"] == 1001
        assert rows[0]["FullName"] == "Alice Nguyen"
        assert rows[0]["Email"] == "alice@example.com"
        assert rows[0]["Active"] is True
        assert rows[0]["Tariff"] == "Hot Desk Monthly"

    def test_string_tariff(self):
        records = [
            {
                "Id": 1002,
                "FullName": "Bob",
                "Email": "bob@example.com",
                "Active": False,
                "Tariff": "Dedicated Desk",
            }
        ]
        rows = build_rows(records)
        assert rows[0]["Tariff"] == "Dedicated Desk"

    def test_empty_records(self):
        assert build_rows([]) == []

    def test_multiple_records(self):
        records = [
            {"Id": 1, "FullName": "A", "Email": "a@x.com", "Active": True, "Tariff": None},
            {"Id": 2, "FullName": "B", "Email": "b@x.com", "Active": False, "Tariff": "Plan B"},
        ]
        rows = build_rows(records)
        assert len(rows) == 2
        assert rows[0]["Tariff"] == ""
        assert rows[1]["Tariff"] == "Plan B"


class TestWriteCsv:
    def test_writes_to_file(self, tmp_path):
        rows = [{"Id": 1, "FullName": "Test User", "Email": "test@example.com", "Active": True, "Tariff": ""}]
        out_file = tmp_path / "members.csv"
        write_csv(rows, str(out_file))
        content = out_file.read_text()
        assert "Id,FullName,Email,Active,Tariff" in content
        assert "Test User" in content

    def test_writes_header_and_rows(self, tmp_path):
        rows = [
            {"Id": 1, "FullName": "Alice", "Email": "alice@example.com", "Active": True, "Tariff": "Hot Desk"},
            {"Id": 2, "FullName": "Bob", "Email": "bob@example.com", "Active": False, "Tariff": "Dedicated Desk"},
        ]
        out_file = tmp_path / "out.csv"
        write_csv(rows, str(out_file))
        with out_file.open() as f:
            parsed = list(csv.DictReader(f))
        assert parsed[0]["FullName"] == "Alice"
        assert parsed[1]["FullName"] == "Bob"

    def test_writes_to_stdout(self, capsys):
        rows = [{"Id": 42, "FullName": "Test", "Email": "t@test.com", "Active": True, "Tariff": ""}]
        write_csv(rows)
        captured = capsys.readouterr()
        assert "Id,FullName,Email,Active,Tariff" in captured.out
        assert "42" in captured.out
