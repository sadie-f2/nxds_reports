"""
Tests for the two-pass LinkedResourceIds grouping logic in resources.py.
"""

import pytest

from app.resources import build_resources, _build_linked_map, _extract_shop


SHOP_RECORDS = [
    {"Id": 1, "Name": "DigiFab",    "ResourceTypeName": "Shop", "LinkedResourceIds": "10,11"},
    {"Id": 2, "Name": "Wood Shop",  "ResourceTypeName": "Shop", "LinkedResourceIds": "12"},
]

TOOL_RECORDS = [
    {"Id": 10, "Name": "DigiFab | Laser Cutter | Calico", "ResourceTypeName": "Tool"},
    {"Id": 11, "Name": "DigiFab | Laser Cutter | Hobbes", "ResourceTypeName": "Tool"},
    {"Id": 12, "Name": "Wood Shop | ShopBot",             "ResourceTypeName": "Tool"},
    # orphan: not in any LinkedResourceIds, has pipe name
    {"Id": 99, "Name": "Fiber Arts | Loom",               "ResourceTypeName": "Tool"},
    # orphan: not in any LinkedResourceIds, no pipe
    {"Id": 98, "Name": "Mystery Tool",                    "ResourceTypeName": "Tool"},
]

ALL_RECORDS = SHOP_RECORDS + TOOL_RECORDS


def test_linked_shop_wins_over_name_parsing():
    """Tools in LinkedResourceIds use the Shop record's name, not parsed name."""
    resources = build_resources(ALL_RECORDS)
    by_id = {r.id: r for r in resources}
    assert by_id[10].shop == "DigiFab"
    assert by_id[11].shop == "DigiFab"
    assert by_id[12].shop == "Wood Shop"


def test_name_parsing_fallback_for_orphan_with_pipe():
    """Tools not linked to any Shop fall back to pipe-split name."""
    resources = build_resources(ALL_RECORDS)
    by_id = {r.id: r for r in resources}
    assert by_id[99].shop == "Fiber Arts"


def test_orphan_with_no_pipe_uses_full_name():
    """Tool with no pipe and no linked shop uses its full name as shop."""
    resources = build_resources(ALL_RECORDS)
    by_id = {r.id: r for r in resources}
    assert by_id[98].shop == "Mystery Tool"


def test_shop_records_excluded_from_result():
    """Shop records must never appear in the returned list."""
    resources = build_resources(ALL_RECORDS)
    ids = {r.id for r in resources}
    assert 1 not in ids  # DigiFab shop
    assert 2 not in ids  # Wood Shop shop
    resource_types = {r.resource_type for r in resources}
    assert "Shop" not in resource_types


def test_sort_order():
    """Results are sorted by (shop, name)."""
    resources = build_resources(ALL_RECORDS)
    keys = [(r.shop, r.name) for r in resources]
    assert keys == sorted(keys)


def test_build_linked_map_ignores_non_shop():
    """_build_linked_map only processes Shop records."""
    records = [
        {"Id": 1, "Name": "MyShop", "ResourceTypeName": "Shop", "LinkedResourceIds": "5,6"},
        {"Id": 5, "Name": "MyShop | Tool A", "ResourceTypeName": "Tool", "LinkedResourceIds": "99"},
    ]
    linked = _build_linked_map(records)
    assert linked == {5: "MyShop", 6: "MyShop"}
    assert 99 not in linked


def test_build_linked_map_handles_missing_linked_ids():
    """Shop records with no LinkedResourceIds are skipped gracefully."""
    records = [
        {"Id": 1, "Name": "EmptyShop", "ResourceTypeName": "Shop", "LinkedResourceIds": None},
        {"Id": 2, "Name": "AlsoEmpty", "ResourceTypeName": "Shop"},
    ]
    linked = _build_linked_map(records)
    assert linked == {}


def test_only_tool_records_returned():
    """build_resources only returns Tool records, regardless of what's in the list."""
    records = [
        {"Id": 1, "Name": "S", "ResourceTypeName": "Shop", "LinkedResourceIds": ""},
        {"Id": 2, "Name": "T", "ResourceTypeName": "Tool"},
    ]
    resources = build_resources(records)
    assert len(resources) == 1
    assert resources[0].id == 2
