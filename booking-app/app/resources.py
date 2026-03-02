"""
GET /api/resources — list all bookable resources.
Cached for 5 minutes; resources change rarely.
"""

from fastapi import APIRouter

from . import cache, nexudus
from .models import Resource

router = APIRouter()

CACHE_KEY = "resources"
CACHE_TTL = 300  # 5 minutes


def _extract_shop(name: str) -> str:
    """Extract shop name from resource name using | separator.
    "DigiFab | Laser Cutter | Calico" → "DigiFab"
    """
    parts = name.split("|")
    return parts[0].strip() if parts else name


def _build_linked_map(records: list[dict]) -> dict[int, str]:
    """Map tool_id → shop_name from LinkedResourceIds on Shop records."""
    linked = {}
    for r in records:
        if r.get("ResourceTypeName") != "Shop":
            continue
        shop_name = r.get("Name") or ""
        raw = r.get("LinkedResourceIds") or ""
        for part in raw.split(","):
            part = part.strip()
            if part.isdigit():
                linked[int(part)] = shop_name
    return linked


def build_resources(records: list[dict]) -> list[Resource]:
    """Two-pass build: LinkedResourceIds for shop, fall back to name-parsing."""
    linked_map = _build_linked_map(records)
    tools = [r for r in records if r.get("ResourceTypeName") == "Tool"]
    result = []
    for r in tools:
        name = r.get("Name") or ""
        shop = linked_map.get(r["Id"]) or _extract_shop(name)
        result.append(Resource(
            id=r["Id"],
            name=name,
            shop=shop,
            resource_type=r.get("ResourceTypeName") or "",
        ))
    return sorted(result, key=lambda r: (r.shop, r.name))


@router.get("/resources", response_model=list[Resource])
def list_resources():
    cached = cache.get(CACHE_KEY, ttl=CACHE_TTL)
    if cached is not None:
        return cached
    records = nexudus.fetch_resources()
    resources = build_resources(records)
    cache.set(CACHE_KEY, resources)
    return resources
