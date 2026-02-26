#!/usr/bin/env python3
"""
report_new_memberships.py — Export new Nexudus contracts over a date range.

Usage:
    NEXUDUS_MOCK=1 python report_new_memberships.py                        # last 30 days
    NEXUDUS_MOCK=1 python report_new_memberships.py --days 60
    NEXUDUS_MOCK=1 python report_new_memberships.py --from 2026-01-01 --to 2026-02-22
    NEXUDUS_MOCK=1 python report_new_memberships.py --file out.csv
    NEXUDUS_MOCK=1 python report_new_memberships.py --output excel --file out.xlsx
"""

import argparse
import csv
import sys
from datetime import date, timedelta

import openpyxl

import nexudus

COLUMNS = ["Id", "CoworkerFullName", "CoworkerEmail", "TariffName", "StartDate", "EndDate"]
ENDPOINT = "/billing/coworkercontracts"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Export new Nexudus memberships over a date range."
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
        "--days",
        type=int,
        default=30,
        metavar="N",
        help="Number of days back from today (default: 30); overridden by --from/--to",
    )
    parser.add_argument(
        "--from",
        dest="from_date",
        metavar="YYYY-MM-DD",
        help="Start date (inclusive); overrides --days",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        metavar="YYYY-MM-DD",
        help="End date (inclusive); overrides --days",
    )
    return parser.parse_args()


def resolve_date_range(args):
    """Return (from_date_str, to_date_str) as ISO 8601 strings."""
    today = date.today()
    if args.from_date or args.to_date:
        from_str = args.from_date or (today - timedelta(days=args.days)).isoformat()
        to_str = args.to_date or today.isoformat()
    else:
        from_str = (today - timedelta(days=args.days)).isoformat()
        to_str = today.isoformat()
    return from_str, to_str


def build_rows(records):
    """Convert raw API records to flat dicts with the desired columns."""
    rows = []
    for rec in records:
        end = rec.get("EndDate") or ""
        rows.append(
            {
                "Id": rec.get("Id", ""),
                "CoworkerFullName": rec.get("CoworkerFullName", ""),
                "CoworkerEmail": rec.get("CoworkerEmail", ""),
                "TariffName": rec.get("TariffName", ""),
                "StartDate": (rec.get("StartDate") or "")[:10],
                "EndDate": end[:10] if end else "",
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
    ws.title = "New Memberships"
    ws.append(COLUMNS)
    for row in rows:
        ws.append([row[col] for col in COLUMNS])

    wb.save(file_path)
    print(f"Wrote {len(rows)} rows to {file_path}", file=sys.stderr)


def main():
    args = parse_args()
    from_str, to_str = resolve_date_range(args)
    print(f"Date range: {from_str} to {to_str}", file=sys.stderr)

    config = nexudus.load_config()
    base_url = config["base_url"]

    extra_params = {
        "from_CoworkerContract_StartDate": from_str,
        "to_CoworkerContract_StartDate": to_str,
    }

    if config["mock"]:
        print("Mock mode enabled — using local test data.", file=sys.stderr)
        response_json = nexudus._mock_response(ENDPOINT)
        records = nexudus.extract_value(response_json)
    else:
        headers = nexudus.make_auth_header(config)
        records = nexudus.get_all(
            base_url, ENDPOINT, headers, size=args.size, extra_params=extra_params
        )

    rows = build_rows(records)
    print(f"Found {len(rows)} new membership(s).", file=sys.stderr)

    if args.output == "excel":
        write_excel(rows, args.file)
    else:
        write_csv(rows, args.file)


if __name__ == "__main__":
    main()
