#!/usr/bin/env python3
"""
report_studio_deposits.py — Security deposits held for current studio renters.

Starts from active studio contracts (source of truth for who is renting),
joins outstanding security deposit records by member ID. Sorted by studio
size (50 → 100 → 200 sq/ft) then member name.

Usage:
    python report_studio_deposits.py                        # CSV to stdout
    python report_studio_deposits.py --file deposits.csv
    python report_studio_deposits.py --output excel --file deposits.xlsx
    python report_studio_deposits.py --missing             # only renters with no deposit on file
"""

import argparse
import csv
import re
import sys
from collections import defaultdict

import openpyxl

import nexudus

CONTRACTS_ENDPOINT = "/billing/coworkercontracts"
DEPOSITS_ENDPOINT = "/billing/contractdeposits"

COLUMNS = [
    "StudioSize",
    "Studio",
    "MemberName",
    "MemberEmail",
    "Plan",
    "DepositAmount",
    "DepositCount",
    "DepositProducts",
    "OldestDepositDate",
    "HasDeposit",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Security deposits held for current studio renters."
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
        "--missing",
        action="store_true",
        help="Show only renters with no deposit on file",
    )
    return parser.parse_args()


def extract_studio_size(tariff_name):
    """Extract numeric sq/ft from tariff name, e.g. '100SF Studio ...' -> 100."""
    if not tariff_name:
        return 9999
    m = re.search(r"(\d+)\s*SF", tariff_name, re.IGNORECASE)
    return int(m.group(1)) if m else 9999


def build_rows(studio_contracts, deposit_records, missing_only=False):
    """
    One row per active studio contract, with aggregated deposit info.
    Deposits matched by CoworkerId (member), not contract ID, so
    contract renewals don't orphan the deposit.
    """
    # Index deposits by member ID — collect all outstanding security deposits per member
    deps_by_member = defaultdict(list)
    for d in deposit_records:
        deps_by_member[d.get("CoworkerContractCoworkerId")].append(d)

    rows = []
    for contract in studio_contracts:
        member_id = contract.get("CoworkerId")
        member_deps = deps_by_member.get(member_id, [])

        has_deposit = len(member_deps) > 0

        if missing_only and has_deposit:
            continue

        if has_deposit:
            total_amount = sum(d.get("Price") or 0 for d in member_deps)
            products = "; ".join(sorted(set(d.get("ProductName", "") for d in member_deps)))
            oldest_date = min(
                (d.get("InvoicedOn") or d.get("CreatedOn") or "")
                for d in member_deps
            )
            oldest_date = oldest_date[:10] if oldest_date else ""
        else:
            total_amount = 0
            products = ""
            oldest_date = ""

        tariff = contract.get("TariffName", "")
        studio_size = extract_studio_size(tariff)
        studio_label = f"{studio_size} sq/ft" if studio_size != 9999 else "unknown"

        rows.append({
            "StudioSize": studio_size,
            "Studio": contract.get("FloorPlanDeskNames") or "",
            "MemberName": contract.get("CoworkerFullName", ""),
            "MemberEmail": contract.get("CoworkerEmail", ""),
            "Plan": tariff,
            "DepositAmount": f"{total_amount:.2f}" if has_deposit else "",
            "DepositCount": len(member_deps) if has_deposit else 0,
            "DepositProducts": products,
            "OldestDepositDate": oldest_date,
            "HasDeposit": "yes" if has_deposit else "NO",
        })

    # Sort: studio size ascending, then member name
    rows.sort(key=lambda r: (r["StudioSize"], r["MemberName"].lower()))

    # Replace numeric size with label for output
    for r in rows:
        size = r["StudioSize"]
        r["StudioSize"] = f"{size} sq/ft" if size != 9999 else "unknown"

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
    """Write rows as Excel (.xlsx)."""
    if not file_path:
        print("ERROR: --file is required for Excel output.", file=sys.stderr)
        sys.exit(1)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Studio Deposits"
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
        print("Mock mode — deposit report requires live data.", file=sys.stderr)
        sys.exit(1)

    headers = nexudus.make_auth_header(config)

    print("Fetching active studio contracts...", file=sys.stderr)
    all_active = nexudus.get_all(base_url, CONTRACTS_ENDPOINT, headers, size=args.size,
                                  extra_params={"CoworkerContract_Active": "true"})
    studio_contracts = [r for r in all_active
                        if "studio" in (r.get("TariffName") or "").lower()]
    print(f"Active studio contracts: {len(studio_contracts)}", file=sys.stderr)

    print("Fetching outstanding security deposits...", file=sys.stderr)
    all_deps = nexudus.get_all(base_url, DEPOSITS_ENDPOINT, headers, size=args.size,
                                extra_params={
                                    "ContractDeposit_Invoiced": "true",
                                    "ContractDeposit_Credited": "false",
                                })
    sec_deps = [d for d in all_deps
                if "security deposit" in (d.get("ProductName") or "").lower()]
    print(f"Outstanding security deposit records: {len(sec_deps)}", file=sys.stderr)

    rows = build_rows(studio_contracts, sec_deps, missing_only=args.missing)

    total = sum(float(r["DepositAmount"]) for r in rows if r["DepositAmount"])
    missing = sum(1 for r in rows if r["HasDeposit"] == "NO")
    print(f"Rows in report: {len(rows)}", file=sys.stderr)
    print(f"Total deposits held: ${total:,.2f}", file=sys.stderr)
    if missing:
        print(f"Renters with no deposit on file: {missing}", file=sys.stderr)

    if args.output == "excel":
        write_excel(rows, args.file)
    else:
        write_csv(rows, args.file)


if __name__ == "__main__":
    main()
