"""
GET /api/members/search?q= — member name search for the booking name picker.

Returns active members whose name or email contains the query string.
Cached for 24 hours; member list changes rarely.
"""

from fastapi import APIRouter, Query

from . import cache, nexudus
from .models import MemberResult

router = APIRouter()

CACHE_KEY = "members"
CACHE_TTL = 86400  # 24 hours


def _load_members() -> list[MemberResult]:
    cached = cache.get(CACHE_KEY, ttl=CACHE_TTL)
    if cached is not None:
        return cached

    records = nexudus.fetch_members()

    # Deduplicate by CoworkerId — multiple contracts per member
    seen: set[int] = set()
    members = []
    for rec in records:
        mid = rec.get("CoworkerId")
        if mid in seen:
            continue
        seen.add(mid)
        members.append(
            MemberResult(
                id=mid,
                name=rec.get("CoworkerFullName") or "",
                email=rec.get("CoworkerEmail") or "",
            )
        )

    members.sort(key=lambda m: m.name.lower())
    cache.set(CACHE_KEY, members)
    return members


@router.get("/members/search", response_model=list[MemberResult])
def search_members(
    q: str = Query(default="", min_length=0, description="Name or email fragment"),
):
    members = _load_members()
    if not q:
        return members[:50]  # return first 50 when no query (kiosk initial state)

    q_lower = q.lower()
    results = [
        m for m in members
        if q_lower in m.name.lower() or q_lower in m.email.lower()
    ]
    return results[:50]
