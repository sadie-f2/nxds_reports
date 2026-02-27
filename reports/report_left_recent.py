#!/usr/bin/env python3
"""
report_lapsed.py — Members with no active contract, showing when their last plan was cancelled.

Usage:
    NEXUDUS_MOCK=1 python report_lapsed.py                   # all lapsed members
    python report_lapsed.py --days 90                        # lapsed within last 90 days
    python report_lapsed.py --days 30 --file winback.csv     # recent lapsed, export to file
    python report_lapsed.py --output excel --file lapsed.xlsx
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

COLUMNS = [
    "CoworkerFullName",
    "CoworkerEmail",
    "LastPlan",
    "CancellationDate",
    "DaysSinceCancellation",
]

ENDPOINT = "/billing/coworkercontracts"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Export lapsed members — those with no active contract."
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
        default=None,
        metavar="N",
        help="Only show members who lapsed within the last N days (default: all)",
    )
    return parser.parse_args()


def parse_date(date_str):
    """Parse an ISO 8601 date string, returning a date object or None."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.rstrip("Z")).date()
    except ValueError:
        return None


def build_rows(active_records, inactive_records, days_filter=None):
    """
    Return one row per lapsed member: those who appear in inactive contracts
    but have no active contract, showing their most recent cancellation.
    """
    active_emails = set(
        r.get("CoworkerEmail", "") for r in active_records if r.get("CoworkerEmail")
    )

    # For each email, track the most recent cancellation
    last_cancel = defaultdict(lambda: {"name": "", "plan": "", "date": "", "date_obj": None})
    for rec in inactive_records:
        email = rec.get("CoworkerEmail", "")
        if not email or email in active_emails:
            continue
        cancel_str = rec.get("CancellationDate") or rec.get("EndDate") or ""
        cancel_date = parse_date(cancel_str)
        existing = last_cancel[email]["date_obj"]
        if cancel_date and (existing is None or cancel_date > existing):
            last_cancel[email] = {
                "name": rec.get("CoworkerFullName", ""),
                "email": email,
                "plan": rec.get("TariffName", ""),
                "date": cancel_str,
                "date_obj": cancel_date,
            }

    today = date.today()
    cutoff = (today - timedelta(days=days_filter)) if days_filter else None

    rows = []
    for data in last_cancel.values():
        d = data["date_obj"]
        if d is None:
            continue
        if cutoff and d < cutoff:
            continue
        days_since = (today - d).days
        rows.append({
            "CoworkerFullName": data["name"],
            "CoworkerEmail": data["email"],
            "LastPlan": data["plan"],
            "CancellationDate": data["date"][:10] if data["date"] else "",
            "DaysSinceCancellation": days_since,
        })

    rows.sort(key=lambda r: r["DaysSinceCancellation"])
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
    ws.title = "Lapsed Members"
    ws.append(COLUMNS)
    for row in rows:
        ws.append([row[col] for col in COLUMNS])
    wb.save(file_path)
    print(f"Wrote {len(rows)} rows to {file_path}", file=sys.stderr)


def main():
    args = parse_args()

    if args.days:
        print(f"Lapsed within last {args.days} days", file=sys.stderr)
    else:
        print("All lapsed members (no day filter)", file=sys.stderr)

    config = nexudus.load_config()
    base_url = config["base_url"]

    if config["mock"]:
        print("Mock mode enabled — using local test data.", file=sys.stderr)
        response_json = nexudus._mock_response(ENDPOINT)
        all_records = nexudus.extract_value(response_json)
        active_records = [r for r in all_records if r.get("Active") is True]
        inactive_records = [r for r in all_records if r.get("Active") is not True]
    else:
        headers = nexudus.make_auth_header(config)
        print("Fetching active contracts...", file=sys.stderr)
        active_records = nexudus.get_all(
            base_url, ENDPOINT, headers, size=args.size,
            extra_params={"CoworkerContract_Active": "true"},
        )
        print("Fetching inactive contracts...", file=sys.stderr)
        inactive_records = nexudus.get_all(
            base_url, ENDPOINT, headers, size=args.size,
            extra_params={"CoworkerContract_Active": "false"},
        )

    print(f"Active contracts: {len(active_records)}", file=sys.stderr)
    print(f"Inactive contracts: {len(inactive_records)}", file=sys.stderr)

    rows = build_rows(active_records, inactive_records, days_filter=args.days)
    print(f"Lapsed members: {len(rows)}", file=sys.stderr)

    if args.output == "excel":
        write_excel(rows, args.file)
    else:
        write_csv(rows, args.file)


if __name__ == "__main__":
    main()
