#!/usr/bin/env python3
"""
report_resource_tree.py — Display all Nexudus resources as a shop/tool tree.

Fetches all resources, groups tools under their parent shop via LinkedResourceIds,
and prints a human-readable tree with C-style braces.

Usage:
    python reports/report_resource_tree.py                    # print to stdout
    python reports/report_resource_tree.py --file /tmp/out.txt
"""

import argparse
import sys

import pathlib as _pathlib
_sys = sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent.parent))
import nexudus


def parse_args():
    parser = argparse.ArgumentParser(
        description="Display Nexudus resources as a shop/tool tree."
    )
    parser.add_argument(
        "--file",
        metavar="PATH",
        help="Output file path (default: stdout)",
    )
    return parser.parse_args()


def fetch_all_resources(config):
    print("Fetching resources...", file=sys.stderr)
    if config["mock"]:
        raw = nexudus._mock_response("/spaces/resources")
        return raw.get("Records", [])
    headers = nexudus.make_auth_header(config)
    return nexudus.get_all(config["base_url"], "/spaces/resources", headers)


def build_tree(records):
    """
    Returns:
        shops      — list of shop records, each with injected '_linked' tool list
        orphans    — tools not linked to any shop
        other      — resources that are neither Shop nor Tool
    """
    by_id = {r["Id"]: r for r in records}

    # Collect IDs claimed by a shop
    claimed_ids = set()
    shops = []
    for r in records:
        if r.get("ResourceTypeName") == "Shop":
            linked_str = r.get("LinkedResourceIds") or ""
            linked_ids = [int(x) for x in linked_str.split(",") if x.strip().isdigit()]
            claimed_ids.update(linked_ids)
            r = dict(r)  # don't mutate original
            r["_linked"] = [by_id[i] for i in linked_ids if i in by_id]
            shops.append(r)

    shops.sort(key=lambda r: r.get("Name") or "")

    tools = [r for r in records if r.get("ResourceTypeName") == "Tool"]
    orphans = sorted(
        [t for t in tools if t["Id"] not in claimed_ids],
        key=lambda r: r.get("Name") or "",
    )

    other = sorted(
        [r for r in records
         if r.get("ResourceTypeName") not in ("Shop", "Tool")],
        key=lambda r: (r.get("ResourceTypeName") or "", r.get("Name") or ""),
    )

    return shops, orphans, other


def render(shops, orphans, other, generated_at=None):
    from datetime import datetime, timezone
    ts = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    tool_count = sum(
        1 for s in shops for t in s["_linked"] if t.get("ResourceTypeName") == "Tool"
    )

    lines = [
        "=" * 72,
        "Artisans Asylum — Nexudus Resource Tree",
        f"Generated: {ts}",
        f"Shops: {len(shops)}  |  Tools (linked): {tool_count}  |  "
        f"Orphaned tools: {len(orphans)}  |  Other resources: {len(other)}",
        "=" * 72,
        "",
        "STRUCTURE",
        "  Each top-level entry is a Shop resource from Nexudus.",
        "  Children are resources linked via Nexudus LinkedResourceIds.",
        "  Resource type and Nexudus ID are shown in [brackets].",
        "",
        "SECTIONS",
        "  Regular shops    — bookable shop spaces with linked tools",
        "  ORPHANED         — Tool resources not linked to any shop",
        "  OTHER            — Non-shop/tool resources (classrooms, flex spaces, etc.)",
        "",
        "NOTES",
        "  'Event Day' entries appear as Shop type in Nexudus and are linked",
        "  bidirectionally to individual shops (whole-facility block-outs).",
        "  Zero-width space characters in DigiFab tool names are a known",
        "  data quality issue in Nexudus.",
        "=" * 72,
        "",
    ]

    for shop in shops:
        name = shop.get("Name") or "(unnamed)"
        rtype = shop.get("ResourceTypeName") or "?"
        rid = shop.get("Id")
        lines.append(f"{name}  [{rtype}, id:{rid}] {{")
        for tool in shop["_linked"]:
            tname = tool.get("Name") or "(unnamed)"
            ttype = tool.get("ResourceTypeName") or "?"
            tid = tool.get("Id")
            lines.append(f"    {tname}  [{ttype}, id:{tid}]")
        lines.append("}")
        lines.append("")

    if orphans:
        lines.append("ORPHANED (not linked to any shop) {")
        for tool in orphans:
            tname = tool.get("Name") or "(unnamed)"
            ttype = tool.get("ResourceTypeName") or "?"
            tid = tool.get("Id")
            lines.append(f"    {tname}  [{ttype}, id:{tid}]")
        lines.append("}")
        lines.append("")

    if other:
        lines.append("OTHER {")
        for r in other:
            rname = r.get("Name") or "(unnamed)"
            rtype = r.get("ResourceTypeName") or "?"
            rid = r.get("Id")
            lines.append(f"    {rname}  [{rtype}, id:{rid}]")
        lines.append("}")
        lines.append("")

    return "\n".join(lines)


def main():
    args = parse_args()
    config = nexudus.load_config()

    records = fetch_all_resources(config)
    print(f"Fetched {len(records)} resources.", file=sys.stderr)

    shops, orphans, other = build_tree(records)
    print(
        f"Shops: {len(shops)}  Tools: {sum(len(s['_linked']) for s in shops)} linked + {len(orphans)} orphaned  Other: {len(other)}",
        file=sys.stderr,
    )

    output = render(shops, orphans, other)

    if args.file:
        with open(args.file, "w") as f:
            f.write(output)
        print(f"Written to {args.file}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
