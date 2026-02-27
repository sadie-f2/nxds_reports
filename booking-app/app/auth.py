"""
POST /api/auth/identify — email-based identity check.

No password. Member enters their email; if it matches an active member
in Nexudus, they're identified and can proceed on their own behalf.
This is trust-first auth: we verify identity, not credentials.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import cache, nexudus
from .members import _load_members

router = APIRouter()


class IdentifyRequest(BaseModel):
    email: str


class IdentifyResponse(BaseModel):
    id: int
    name: str
    email: str


@router.post("/auth/identify", response_model=IdentifyResponse)
def identify(req: IdentifyRequest):
    email = req.email.strip().lower()
    members = _load_members()
    match = next((m for m in members if m.email.lower() == email), None)
    if not match:
        raise HTTPException(status_code=404, detail="No active member found with that email address.")
    return IdentifyResponse(id=match.id, name=match.name, email=match.email)
