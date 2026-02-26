#!/usr/bin/env python3
"""
report_arrears.py — Export unpaid Nexudus invoices (accounts in arrears).

Usage:
    NEXUDUS_MOCK=1 python report_arrears.py                         # sorted by age (oldest first)
    NEXUDUS_MOCK=1 python report_arrears.py --sort value            # sorted by amount (largest first)
    NEXUDUS_MOCK=1 python report_arrears.py --file out.csv
    NEXUDUS_MOCK=1 python report_arrears.py --output excel --file out.xlsx
"""

import argparse
import csv
import sys
from datetime import date, datetime

import openpyxl

import nexudus

COLUMNS = [
    "Id",
    "CoworkerFullName",
    "CoworkerEmail",
    "InvoiceNumber",
    "TotalAmount",
    "DueDate",
    "DaysOverdue",
]
ENDPOINT = "/billing/coworkerinvoices"
CONTRACTS_ENDPOINT = "/billing/coworkercontracts"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Export unpaid Nexudus invoices sorted by age or value."
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
        "--sort",
        choices=["age", "value"],
        default="age",
        help="Sort order: 'age' = oldest overdue first, 'value' = largest amount first (default: age)",
    )
    return parser.parse_args()


def parse_due_date(due_date_str):
    """Parse an ISO 8601 date string, returning a date object or None."""
    if not due_date_str:
        return None
    try:
        return datetime.fromisoformat(due_date_str.rstrip("Z")).date()
    except ValueError:
        return None


def compute_days_overdue(due_date):
    """Return max(0, days since due_date). Invoices not yet due return 0."""
    if due_date is None:
        return 0
    return max(0, (date.today() - due_date).days)


def build_email_lookup(contract_records):
    """Build a CoworkerId -> email dict from active contract records."""
    lookup = {}
    for rec in contract_records:
        cid = rec.get("CoworkerId")
        email = rec.get("CoworkerEmail", "")
        if cid and email and cid not in lookup:
            lookup[cid] = email
    return lookup


def build_rows(records, email_lookup=None):
    """Convert raw API records to flat dicts, computing DaysOverdue."""
    if email_lookup is None:
        email_lookup = {}
    rows = []
    for rec in records:
        due_date = parse_due_date(rec.get("DueDate", ""))
        coworker_id = rec.get("CoworkerId")
        rows.append(
            {
                "Id": rec.get("Id", ""),
                "CoworkerFullName": rec.get("CoworkerFullName", ""),
                "CoworkerEmail": email_lookup.get(coworker_id, ""),
                "InvoiceNumber": rec.get("InvoiceNumber", ""),
                "TotalAmount": rec.get("TotalAmount", ""),
                "DueDate": rec.get("DueDate", ""),
                "DaysOverdue": compute_days_overdue(due_date),
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
    ws.title = "Arrears"
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
        response_json = nexudus._mock_response(ENDPOINT)
        records = nexudus.extract_value(response_json)
        records = [r for r in records if r.get("Paid") is not True]
        email_lookup = {}
    else:
        headers = nexudus.make_auth_header(config)
        records = nexudus.get_all(
            base_url, ENDPOINT, headers, size=args.size,
            extra_params={"CoworkerInvoice_Paid": "false"},
        )
        print("Fetching active contracts for email lookup...", file=sys.stderr)
        contract_records = nexudus.get_all(
            base_url, CONTRACTS_ENDPOINT, headers, size=args.size,
            extra_params={"CoworkerContract_Active": "true"},
        )
        email_lookup = build_email_lookup(contract_records)
        print(f"Loaded {len(email_lookup)} member emails.", file=sys.stderr)

    print(f"Unpaid invoices: {len(records)}", file=sys.stderr)

    rows = build_rows(records, email_lookup)

    if args.sort == "value":
        rows.sort(key=lambda r: r["TotalAmount"], reverse=True)
    else:
        rows.sort(key=lambda r: r["DaysOverdue"], reverse=True)

    if args.output == "excel":
        write_excel(rows, args.file)
    else:
        write_csv(rows, args.file)


if __name__ == "__main__":
    main()
