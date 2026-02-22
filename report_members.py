#!/usr/bin/env python3
"""
report_members.py — Export Nexudus coworker/member data to CSV or Excel.

Usage:
    NEXUDUS_MOCK=1 python report_members.py                  # CSV to stdout
    NEXUDUS_MOCK=1 python report_members.py --file out.csv   # CSV to file
    NEXUDUS_MOCK=1 python report_members.py --output excel --file out.xlsx
    NEXUDUS_MOCK=1 python report_members.py --active-only
"""

import argparse
import csv
import sys

import openpyxl

import nexudus

COLUMNS = ["Id", "FullName", "Email", "Active", "Tariff"]
ENDPOINT = "/spaces/coworkers"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Export Nexudus member data to CSV or Excel."
    )
    parser.add_argument(
        "--output",
        choices=["csv", "excel"],
        default="csv",
        help="Output format (default: csv)",
    )
    parser.add_argument(
        "--file",
        metavar="PATH",
        help="Output file path. Defaults to stdout for CSV.",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=100,
        metavar="N",
        help="Page size for API requests (default: 100)",
    )
    parser.add_argument(
        "--active-only",
        action="store_true",
        help="Only include active members",
    )
    return parser.parse_args()


def extract_tariff(record):
    """Return tariff name whether Tariff is a string or nested dict."""
    tariff = record.get("Tariff")
    if tariff is None:
        return ""
    if isinstance(tariff, dict):
        return tariff.get("Name", "")
    return str(tariff)


def build_rows(records):
    """Convert raw API records to flat dicts with the desired columns."""
    rows = []
    for rec in records:
        rows.append(
            {
                "Id": rec.get("Id", ""),
                "FullName": rec.get("FullName", ""),
                "Email": rec.get("Email", ""),
                "Active": rec.get("Active", ""),
                "Tariff": extract_tariff(rec),
            }
        )
    return rows


def write_csv(rows, file_path=None):
    """Write rows as CSV. Uses stdout if file_path is None."""
    if file_path:
        fh = open(file_path, "w", newline="", encoding="utf-8")
    else:
        fh = sys.stdout

    try:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    finally:
        if file_path:
            fh.close()

    if file_path:
        print(f"Wrote {len(rows)} rows to {file_path}", file=sys.stderr)


def write_excel(rows, file_path):
    """Write rows as Excel (.xlsx) using openpyxl."""
    if not file_path:
        print("ERROR: --file is required for Excel output.", file=sys.stderr)
        sys.exit(1)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Members"
    ws.append(COLUMNS)
    for row in rows:
        ws.append([row[col] for col in COLUMNS])

    wb.save(file_path)
    print(f"Wrote {len(rows)} rows to {file_path}", file=sys.stderr)


def main():
    args = parse_args()

    config = nexudus.load_config()
    base_url = config["base_url"]

    if config["mock"]:
        print("Mock mode enabled — using local test data.", file=sys.stderr)
        # In mock mode, bypass HTTP and load canned data directly
        response_json = nexudus._mock_response(ENDPOINT)
        records = nexudus.extract_value(response_json)
    else:
        headers = nexudus.make_auth_header(config)
        records = nexudus.get_all(
            base_url, ENDPOINT, headers, size=args.size
        )

    if args.active_only:
        before = len(records)
        records = [r for r in records if r.get("Active") is True]
        print(
            f"Filtered to active members: {len(records)}/{before}",
            file=sys.stderr,
        )

    rows = build_rows(records)

    if args.output == "excel":
        write_excel(rows, args.file)
    else:
        write_csv(rows, args.file)


if __name__ == "__main__":
    main()
