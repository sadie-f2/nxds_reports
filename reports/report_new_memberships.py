#!/usr/bin/env python3
"""
report_new_memberships.py — Members whose first-ever contract started within a date range.

Unlike report_new_contracts.py (which returns all contracts started in a range,
including add-ons and upgrades for existing members), this report fetches all
contracts and identifies members whose very first contract falls within the
requested period — i.e., genuinely new members.

Usage:
    NEXUDUS_MOCK=1 python report_new_memberships.py                        # last 30 days
    NEXUDUS_MOCK=1 python report_new_memberships.py --days 60
    NEXUDUS_MOCK=1 python report_new_memberships.py --from 2026-01-01 --to 2026-02-25
    python report_new_memberships.py --file new_members.csv
    python report_new_memberships.py --output excel --file new_members.xlsx
"""

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

import openpyxl

import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent.parent))
import nexudus

COLUMNS = ["CoworkerFullName", "CoworkerEmail", "FirstPlan", "FirstStartDate"]
ENDPOINT = "/billing/coworkercontracts"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Export genuinely new members — those whose first-ever contract started in range."
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
    """Return (from_date, to_date) as date objects."""
    today = date.today()
    if args.from_date or args.to_date:
        from_d = date.fromisoformat(args.from_date) if args.from_date else today - timedelta(days=args.days)
        to_d = date.fromisoformat(args.to_date) if args.to_date else today
    else:
        from_d = today - timedelta(days=args.days)
        to_d = today
    return from_d, to_d


def parse_start_date(date_str):
    """Parse an ISO 8601 date string, returning a date object or None."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.rstrip("Z")).date()
    except ValueError:
        return None


def build_rows(all_records, from_date, to_date):
    """
    Return one row per genuinely new member: those whose earliest contract
    StartDate falls within [from_date, to_date].
    """
    # Find earliest contract per member
    earliest = defaultdict(lambda: {"name": "", "plan": "", "date": None, "date_str": ""})
    for rec in all_records:
        email = rec.get("CoworkerEmail", "")
        if not email:
            continue
        start = parse_start_date(rec.get("StartDate", ""))
        if start is None:
            continue
        existing = earliest[email]["date"]
        if existing is None or start < existing:
            earliest[email] = {
                "name": rec.get("CoworkerFullName", ""),
                "plan": rec.get("TariffName", ""),
                "date": start,
                "date_str": rec.get("StartDate", ""),
            }

    # Keep only members whose earliest contract falls in range
    rows = []
    for email, data in earliest.items():
        d = data["date"]
        if d is None or d < from_date or d > to_date:
            continue
        rows.append({
            "CoworkerFullName": data["name"],
            "CoworkerEmail": email,
            "FirstPlan": data["plan"],
            "FirstStartDate": data["date_str"][:10] if data["date_str"] else "",
        })

    rows.sort(key=lambda r: r["FirstStartDate"])
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
    ws.title = "New Members"
    ws.append(COLUMNS)
    for row in rows:
        ws.append([row[col] for col in COLUMNS])
    wb.save(file_path)
    print(f"Wrote {len(rows)} rows to {file_path}", file=sys.stderr)


def main():
    args = parse_args()
    from_date, to_date = resolve_date_range(args)
    print(f"Date range: {from_date} to {to_date}", file=sys.stderr)

    config = nexudus.load_config()
    base_url = config["base_url"]

    if config["mock"]:
        print("Mock mode enabled — using local test data.", file=sys.stderr)
        response_json = nexudus._mock_response(ENDPOINT)
        all_records = nexudus.extract_value(response_json)
    else:
        headers = nexudus.make_auth_header(config)
        print("Fetching all contracts (this determines first-ever start date per member)...", file=sys.stderr)
        all_records = nexudus.get_all(base_url, ENDPOINT, headers, size=args.size)

    print(f"Total contracts fetched: {len(all_records)}", file=sys.stderr)

    rows = build_rows(all_records, from_date, to_date)
    print(f"New members in range: {len(rows)}", file=sys.stderr)

    if args.output == "excel":
        write_excel(rows, args.file)
    else:
        write_csv(rows, args.file)


if __name__ == "__main__":
    main()
