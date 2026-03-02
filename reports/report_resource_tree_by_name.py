#!/usr/bin/env python3
"""
report_resource_tree_by_name.py — Display Nexudus resources as a shop/tool tree
derived from name parsing (the | separator convention used in the booking app).

Compare with report_resource_tree.py which uses LinkedResourceIds from Nexudus.

Usage:
    python reports/report_resource_tree_by_name.py                    # print to stdout
    python reports/report_resource_tree_by_name.py --file /tmp/out.txt
"""

import argparse
import sys

import pathlib as _pathlib
_sys = sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent.parent))
import nexudus


def parse_args():
    parser = argparse.ArgumentParser(
        description="Display Nexudus resources as a shop/tool tree (name-parsed)."
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


def extract_shop(name):
    """Mirror the booking app logic: split on | and take the first segment."""
    parts = name.split("|")
    return parts[0].strip() if len(parts) > 1 else None


def build_tree(records):
    """
    Group Tool resources by the shop prefix in their name (text before first |).
    Tools with no | in their name are ungrouped.
    Non-Tool resources are listed separately.
    """
    shops = {}   # shop_name -> list of tool records
    ungrouped = []
    other = []

    for r in records:
        rtype = r.get("ResourceTypeName") or ""
        name = r.get("Name") or ""

        if rtype == "Tool":
            shop = extract_shop(name)
            if shop:
                shops.setdefault(shop, []).append(r)
            else:
                ungrouped.append(r)
        else:
            other.append(r)

    # Sort shops alphabetically, tools within each shop by name
    sorted_shops = sorted(shops.items(), key=lambda x: x[0].strip().lower())
    sorted_shops = [(s, sorted(tools, key=lambda r: r.get("Name") or ""))
                    for s, tools in sorted_shops]

    ungrouped.sort(key=lambda r: r.get("Name") or "")
    other.sort(key=lambda r: (r.get("ResourceTypeName") or "", r.get("Name") or ""))

    return sorted_shops, ungrouped, other


def render(sorted_shops, ungrouped, other, generated_at=None):
    from datetime import datetime, timezone
    ts = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    tool_count = sum(len(tools) for _, tools in sorted_shops)

    lines = [
        "=" * 72,
        "Artisans Asylum — Nexudus Resource Tree (name-parsed)",
        f"Generated: {ts}",
        f"Shop groups: {len(sorted_shops)}  |  Tools (grouped): {tool_count}  |  "
        f"Ungrouped tools: {len(ungrouped)}  |  Other resources: {len(other)}",
        "=" * 72,
        "",
        "STRUCTURE",
        "  Shop groups are derived by splitting resource names on '|' and taking",
        "  the first segment. This mirrors the booking app's resources.py logic.",
        "  Resource type and Nexudus ID are shown in [brackets].",
        "",
        "SECTIONS",
        "  Shop groups     — Tool resources that have a '|' shop prefix in their name",
        "  UNGROUPED       — Tool resources with no '|' in their name",
        "  OTHER           — Non-Tool resources (shops, classrooms, flex spaces, etc.)",
        "",
        "NOTES",
        "  This is a name-parsing view only — shop groups here are not Nexudus",
        "  entities. Compare with report_resource_tree.py (LinkedResourceIds view).",
        "  Zero-width space characters in DigiFab names cause grouping anomalies.",
        "=" * 72,
        "",
    ]

    for shop_name, tools in sorted_shops:
        lines.append(f"{shop_name}  [name-group] {{")
        for tool in tools:
            tname = tool.get("Name") or "(unnamed)"
            ttype = tool.get("ResourceTypeName") or "?"
            tid = tool.get("Id")
            lines.append(f"    {tname}  [{ttype}, id:{tid}]")
        lines.append("}")
        lines.append("")

    if ungrouped:
        lines.append("UNGROUPED (no | in name) {")
        for tool in ungrouped:
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

    sorted_shops, ungrouped, other = build_tree(records)
    print(
        f"Shop groups: {len(sorted_shops)}  Tools: {sum(len(t) for _, t in sorted_shops)} grouped + {len(ungrouped)} ungrouped  Other: {len(other)}",
        file=sys.stderr,
    )

    output = render(sorted_shops, ungrouped, other)

    if args.file:
        with open(args.file, "w") as f:
            f.write(output)
        print(f"Written to {args.file}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
