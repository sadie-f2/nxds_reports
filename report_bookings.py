#!/usr/bin/env python3
"""
report_bookings.py — Export Nexudus bookings over a time range.

Usage:
    NEXUDUS_MOCK=1 python report_bookings.py                          # last 180 days, flat list
    NEXUDUS_MOCK=1 python report_bookings.py --days 90
    NEXUDUS_MOCK=1 python report_bookings.py --from 2025-09-01 --to 2026-02-24
    NEXUDUS_MOCK=1 python report_bookings.py --summary                # group by resource
    NEXUDUS_MOCK=1 python report_bookings.py --resource "laser"       # filter by resource name
    NEXUDUS_MOCK=1 python report_bookings.py --file out.csv
    NEXUDUS_MOCK=1 python report_bookings.py --output excel --file out.xlsx
"""

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import openpyxl

import nexudus

FLAT_COLUMNS = [
    "Shop",
    "ResourceName",
    "BookingNumber",
    "CoworkerFullName",
    "CoworkerEmail",
    "FromTime",
    "ToTime",
    "DurationHours",
]

SUMMARY_COLUMNS = [
    "Shop",
    "ResourceName",
    "BookingCount",
    "TotalHours",
]

ENDPOINT = "/spaces/bookings"
CONTRACTS_ENDPOINT = "/billing/coworkercontracts"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Export Nexudus bookings over a time range."
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
        default=180,
        metavar="N",
        help="Number of days back from today (default: 180)",
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
    parser.add_argument(
        "--resource",
        metavar="TERM",
        help="Filter by resource name (case-insensitive substring match)",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Group by resource: show booking counts and total hours",
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


def extract_shop(resource_name):
    """Extract shop name from resource name using | separator."""
    if "|" in resource_name:
        return resource_name.split("|")[0].strip()
    return resource_name.strip()


EASTERN = ZoneInfo("America/New_York")


def to_eastern(utc_str):
    """Convert a UTC ISO datetime string to Eastern time, formatted YYYY-MM-DD HH:MM."""
    if not utc_str:
        return ""
    try:
        dt = datetime.fromisoformat(utc_str.rstrip("Z")).replace(tzinfo=timezone.utc)
        local = dt.astimezone(EASTERN)
        suffix = local.strftime("%Z")  # "EST" or "EDT"
        return local.strftime("%Y-%m-%d %H:%M ") + suffix
    except ValueError:
        return utc_str


def compute_duration_hours(from_time_str, to_time_str):
    """Compute duration in hours between two ISO datetime strings."""
    if not from_time_str or not to_time_str:
        return ""
    try:
        from_dt = datetime.fromisoformat(from_time_str.rstrip("Z"))
        to_dt = datetime.fromisoformat(to_time_str.rstrip("Z"))
        return round((to_dt - from_dt).total_seconds() / 3600, 2)
    except ValueError:
        return ""


def build_email_lookup(contract_records):
    """Build a CoworkerId -> email dict from active contract records."""
    lookup = {}
    for rec in contract_records:
        cid = rec.get("CoworkerId")
        email = rec.get("CoworkerEmail", "")
        if cid and email and cid not in lookup:
            lookup[cid] = email
    return lookup


def build_flat_rows(records, email_lookup=None):
    """Convert raw booking records to flat dicts."""
    if email_lookup is None:
        email_lookup = {}
    rows = []
    for rec in records:
        resource_name = rec.get("ResourceName", "")
        from_time = rec.get("FromTime", "")
        to_time = rec.get("ToTime", "")
        coworker_id = rec.get("CoworkerId")
        rows.append({
            "Shop": extract_shop(resource_name),
            "ResourceName": resource_name,
            "BookingNumber": rec.get("BookingNumber", ""),
            "CoworkerFullName": rec.get("CoworkerFullName", ""),
            "CoworkerEmail": email_lookup.get(coworker_id, ""),
            "FromTime": to_eastern(from_time),
            "ToTime": to_eastern(to_time),
            "DurationHours": compute_duration_hours(from_time, to_time),
        })
    rows.sort(key=lambda r: (r["Shop"], r["ResourceName"], r["FromTime"]))
    return rows


def build_summary_rows(records):
    """Group bookings by resource, summing counts and hours."""
    summary = defaultdict(lambda: {"count": 0, "total_hours": 0.0})
    for rec in records:
        resource_name = rec.get("ResourceName", "")
        shop = extract_shop(resource_name)
        key = (shop, resource_name)
        summary[key]["count"] += 1
        hours = compute_duration_hours(rec.get("FromTime", ""), rec.get("ToTime", ""))
        if isinstance(hours, float):
            summary[key]["total_hours"] += hours
    rows = []
    for (shop, resource_name), data in sorted(summary.items()):
        rows.append({
            "Shop": shop,
            "ResourceName": resource_name,
            "BookingCount": data["count"],
            "TotalHours": round(data["total_hours"], 2),
        })
    return rows


def write_csv(rows, columns, file_path=None):
    """Write rows as CSV. Uses stdout if file_path is None."""
    if file_path:
        fh = open(file_path, "w", newline="", encoding="utf-8")
    else:
        fh = sys.stdout
    try:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    finally:
        if file_path:
            fh.close()
    if file_path:
        print(f"Wrote {len(rows)} rows to {file_path}", file=sys.stderr)


def write_excel(rows, columns, file_path):
    """Write rows as Excel (.xlsx) using openpyxl."""
    if not file_path:
        print("ERROR: --file is required for Excel output.", file=sys.stderr)
        sys.exit(1)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Bookings"
    ws.append(columns)
    for row in rows:
        ws.append([row[col] for col in columns])
    wb.save(file_path)
    print(f"Wrote {len(rows)} rows to {file_path}", file=sys.stderr)


def main():
    args = parse_args()
    from_str, to_str = resolve_date_range(args)
    print(f"Date range: {from_str} to {to_str}", file=sys.stderr)

    config = nexudus.load_config()
    base_url = config["base_url"]

    if config["mock"]:
        print("Mock mode enabled — using local test data.", file=sys.stderr)
        response_json = nexudus._mock_response(ENDPOINT)
        records = nexudus.extract_value(response_json)
        email_lookup = {}
    else:
        headers = nexudus.make_auth_header(config)
        records = nexudus.get_all(
            base_url, ENDPOINT, headers, size=args.size,
            extra_params={
                "from_Booking_FromTime": from_str,
                "to_Booking_FromTime": to_str,
            },
        )
        print("Fetching active contracts for member filter and emails...", file=sys.stderr)
        contract_records = nexudus.get_all(
            base_url, CONTRACTS_ENDPOINT, headers, size=args.size,
            extra_params={"CoworkerContract_Active": "true"},
        )
        email_lookup = build_email_lookup(contract_records)
        active_member_ids = set(email_lookup.keys())
        print(f"Active members: {len(active_member_ids)}", file=sys.stderr)
        records = [r for r in records if r.get("CoworkerId") in active_member_ids]
        print(f"Bookings by active members: {len(records)}", file=sys.stderr)

    print(f"Bookings fetched: {len(records)}", file=sys.stderr)

    if args.resource:
        term = args.resource.lower()
        records = [r for r in records if term in r.get("ResourceName", "").lower()]
        print(f"Matching '{args.resource}': {len(records)}", file=sys.stderr)

    if args.summary:
        rows = build_summary_rows(records)
        columns = SUMMARY_COLUMNS
    else:
        rows = build_flat_rows(records, email_lookup)
        columns = FLAT_COLUMNS

    if args.output == "excel":
        write_excel(rows, columns, args.file)
    else:
        write_csv(rows, columns, args.file)


if __name__ == "__main__":
    main()
