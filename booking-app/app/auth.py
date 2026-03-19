"""
POST /api/auth/identify — email + password identity check.

Member enters their Nexudus email and password. We first confirm the email
matches an active member in our cached member list, then verify the password
against the Nexudus token endpoint. Admin API credentials are used for all
subsequent data operations — the member token is discarded immediately.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import cache, nexudus
from .members import _load_members

router = APIRouter()


class IdentifyRequest(BaseModel):
    email: str
    password: str


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
    if not nexudus.verify_member_password(email, req.password):
        raise HTTPException(status_code=401, detail="Incorrect password.")
    return IdentifyResponse(id=match.id, name=match.name, email=match.email)
