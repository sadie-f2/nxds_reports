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


def parse_resource(rec: dict) -> Resource:
    name = rec.get("Name") or ""
    return Resource(
        id=rec["Id"],
        name=name,
        shop=_extract_shop(name),
        resource_type=rec.get("ResourceTypeName") or "",
    )


@router.get("/resources", response_model=list[Resource])
def list_resources():
    cached = cache.get(CACHE_KEY, ttl=CACHE_TTL)
    if cached is not None:
        return cached

    records = nexudus.fetch_resources()
    resources = sorted(
        [parse_resource(r) for r in records],
        key=lambda r: (r.shop, r.name),
    )
    cache.set(CACHE_KEY, resources)
    return resources
