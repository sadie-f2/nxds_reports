#!/usr/bin/env python3
"""
report_active_memberships.py — Export active Nexudus contracts, optionally summarised by plan.

Usage:
    NEXUDUS_MOCK=1 python report_active_memberships.py               # unique members (default)
    NEXUDUS_MOCK=1 python report_active_memberships.py --all         # one row per contract
    NEXUDUS_MOCK=1 python report_active_memberships.py --multiples   # members with 2+ contracts
    NEXUDUS_MOCK=1 python report_active_memberships.py --summary     # count by plan type
    NEXUDUS_MOCK=1 python report_active_memberships.py --file out.csv
    NEXUDUS_MOCK=1 python report_active_memberships.py --output excel --file out.xlsx
"""

import argparse
import csv
import sys
from collections import Counter, defaultdict

import openpyxl

import nexudus

COLUMNS_UNIQUE = ["CoworkerFullName", "CoworkerEmail", "ContractCount", "Plans", "EarliestStartDate"]
COLUMNS_FLAT = ["Id", "CoworkerFullName", "CoworkerEmail", "TariffName", "StartDate"]
COLUMNS_SUMMARY = ["TariffName", "MemberCount"]
ENDPOINT = "/billing/coworkercontracts"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Export active Nexudus memberships, optionally grouped by plan type."
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
        "--all",
        action="store_true",
        help="Show all contracts (one row per contract, not deduplicated)",
    )
    parser.add_argument(
        "--multiples",
        action="store_true",
        help="Show only members with two or more active contracts",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Output a count of active members per plan type instead of the full list",
    )
    return parser.parse_args()


def build_flat_rows(records):
    """Convert raw API records to flat dicts for the list view."""
    rows = []
    for rec in records:
        rows.append(
            {
                "Id": rec.get("Id", ""),
                "CoworkerFullName": rec.get("CoworkerFullName", ""),
                "CoworkerEmail": rec.get("CoworkerEmail", ""),
                "TariffName": rec.get("TariffName", ""),
                "StartDate": rec.get("StartDate", ""),
            }
        )
    return rows


def build_unique_rows(records, multiples_only=False):
    """One row per member, with all active plan names concatenated."""
    by_member = defaultdict(lambda: {"name": "", "plans": [], "starts": []})
    for rec in records:
        email = rec.get("CoworkerEmail", "")
        by_member[email]["name"] = rec.get("CoworkerFullName", "")
        by_member[email]["plans"].append(rec.get("TariffName", ""))
        start = rec.get("StartDate", "")
        if start:
            by_member[email]["starts"].append(start)
    rows = []
    for email, data in by_member.items():
        if multiples_only and len(data["plans"]) < 2:
            continue
        rows.append({
            "CoworkerFullName": data["name"],
            "CoworkerEmail": email,
            "ContractCount": len(data["plans"]),
            "Plans": "; ".join(data["plans"]),
            "EarliestStartDate": min(data["starts"]) if data["starts"] else "",
        })
    rows.sort(key=lambda r: r["CoworkerFullName"])
    return rows


def build_summary_rows(records):
    """Count active members per TariffName, sorted descending by count."""
    counts = Counter(rec.get("TariffName", "") for rec in records)
    return [
        {"TariffName": name, "MemberCount": count}
        for name, count in counts.most_common()
    ]


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


def write_excel(rows, columns, sheet_title, file_path):
    """Write rows as Excel (.xlsx) using openpyxl."""
    if not file_path:
        print("ERROR: --file is required for Excel output.", file=sys.stderr)
        sys.exit(1)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_title
    ws.append(columns)
    for row in rows:
        ws.append([row[col] for col in columns])

    wb.save(file_path)
    print(f"Wrote {len(rows)} rows to {file_path}", file=sys.stderr)


def main():
    args = parse_args()

    config = nexudus.load_config()
    base_url = config["base_url"]

    if config["mock"]:
        print("Mock mode enabled — using local test data.", file=sys.stderr)
        response_json = nexudus._mock_response(ENDPOINT)
        records = nexudus.extract_value(response_json)
        records = [r for r in records if r.get("Active") is True]
    else:
        headers = nexudus.make_auth_header(config)
        records = nexudus.get_all(
            base_url, ENDPOINT, headers, size=args.size,
            extra_params={"CoworkerContract_Active": "true"},
        )

    print(f"Active contracts: {len(records)}", file=sys.stderr)

    if args.summary:
        rows = build_summary_rows(records)
        columns = COLUMNS_SUMMARY
        sheet_title = "Active by Plan"
    elif args.all:
        rows = build_flat_rows(records)
        columns = COLUMNS_FLAT
        sheet_title = "Active Memberships (All)"
    elif args.multiples:
        rows = build_unique_rows(records, multiples_only=True)
        columns = COLUMNS_UNIQUE
        sheet_title = "Multiple Contracts"
        print(f"Members with 2+ contracts: {len(rows)}", file=sys.stderr)
    else:
        rows = build_unique_rows(records)
        columns = COLUMNS_UNIQUE
        sheet_title = "Active Members"
        print(f"Unique members: {len(rows)}", file=sys.stderr)

    if args.output == "excel":
        write_excel(rows, columns, sheet_title, args.file)
    else:
        write_csv(rows, columns, args.file)


if __name__ == "__main__":
    main()
