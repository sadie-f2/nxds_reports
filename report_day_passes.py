#!/usr/bin/env python3
"""
report_day_passes.py — Day pass member activity: purchases over a date range.

Fetches active Day Pass Member contracts, then scans invoices for the period
to find actual purchases (non-zero invoiced amounts). Members with zero
purchases in the window are flagged — useful for deciding who to manage
outside Nexudus.

Sorted by total spend ascending (zero-purchase members first).

Usage:
    python report_day_passes.py                             # last 365 days
    python report_day_passes.py --days 180
    python report_day_passes.py --from 2025-01-01 --to 2025-12-31
    python report_day_passes.py --file day_passes.csv
    python report_day_passes.py --output excel --file day_passes.xlsx
"""

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date, timedelta

import openpyxl

import nexudus

CONTRACTS_ENDPOINT = "/billing/coworkercontracts"
INVOICES_ENDPOINT = "/billing/coworkerinvoices"

COLUMNS = [
    "MemberName",
    "MemberEmail",
    "MemberSince",
    "TotalSpend",
    "PurchaseCount",
    "LastPurchaseDate",
]

DAY_PASS_PLAN = "Day Pass Member"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Day pass member purchase activity over a date range."
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
        default=365,
        metavar="N",
        help="Number of days back from today (default: 365)",
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
    today = date.today()
    if args.from_date or args.to_date:
        from_str = args.from_date or (today - timedelta(days=args.days)).isoformat()
        to_str = args.to_date or today.isoformat()
    else:
        from_str = (today - timedelta(days=args.days)).isoformat()
        to_str = today.isoformat()
    return from_str, to_str


def build_rows(day_pass_contracts, invoices):
    """
    One row per day pass member. Invoices with TotalAmount <= 0 are skipped
    (those are the monthly $0 plan billing cycles, not actual purchases).
    Members with no matching invoices appear with zero spend.
    """
    # Index members
    members = {}
    for rec in day_pass_contracts:
        cid = rec.get("CoworkerId")
        if cid:
            members[cid] = {
                "name": rec.get("CoworkerFullName", ""),
                "email": rec.get("CoworkerEmail", ""),
                "since": (rec.get("StartDate") or "")[:10],
            }

    # Aggregate invoice totals per member
    totals = defaultdict(lambda: {"amount": 0.0, "count": 0, "last": ""})
    for inv in invoices:
        cid = inv.get("CoworkerId")
        if cid not in members:
            continue
        amount = inv.get("TotalAmount") or 0
        if amount <= 0:
            continue
        totals[cid]["amount"] += amount
        totals[cid]["count"] += 1
        created = (inv.get("CreatedOn") or "")[:10]
        if created > totals[cid]["last"]:
            totals[cid]["last"] = created

    rows = []
    for cid, m in members.items():
        t = totals[cid]
        rows.append({
            "MemberName": m["name"],
            "MemberEmail": m["email"],
            "MemberSince": m["since"],
            "TotalSpend": round(t["amount"], 2),
            "PurchaseCount": t["count"],
            "LastPurchaseDate": t["last"],
        })

    # Zero-spend members first, then ascending by spend, then by name
    rows.sort(key=lambda r: (r["TotalSpend"], r["MemberName"].lower()))
    return rows


def write_csv(rows, file_path=None):
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
    if not file_path:
        print("ERROR: --file is required for Excel output.", file=sys.stderr)
        sys.exit(1)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Day Pass Members"
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

    if config["mock"]:
        print("ERROR: Mock mode not supported for this report.", file=sys.stderr)
        sys.exit(1)

    headers = nexudus.make_auth_header(config)

    print("Fetching active day pass contracts...", file=sys.stderr)
    all_active = nexudus.get_all(
        base_url, CONTRACTS_ENDPOINT, headers, size=args.size,
        extra_params={"CoworkerContract_Active": "true"},
    )
    day_pass_contracts = [r for r in all_active if r.get("TariffName") == DAY_PASS_PLAN]
    print(f"Day pass members: {len(day_pass_contracts)}", file=sys.stderr)

    print("Fetching invoices for date range...", file=sys.stderr)
    invoices = nexudus.get_all(
        base_url, INVOICES_ENDPOINT, headers, size=args.size,
        extra_params={
            "from_CoworkerInvoice_CreatedOn": from_str,
            "to_CoworkerInvoice_CreatedOn": to_str,
        },
    )
    print(f"Invoices fetched: {len(invoices)}", file=sys.stderr)

    rows = build_rows(day_pass_contracts, invoices)

    zero = sum(1 for r in rows if r["TotalSpend"] == 0)
    total_spend = sum(r["TotalSpend"] for r in rows)
    print(f"Members with zero purchases in range: {zero}/{len(rows)}", file=sys.stderr)
    print(f"Total spend by day pass members: ${total_spend:,.2f}", file=sys.stderr)

    if args.output == "excel":
        write_excel(rows, args.file)
    else:
        write_csv(rows, args.file)


if __name__ == "__main__":
    main()
