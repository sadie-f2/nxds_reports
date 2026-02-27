"""
Pydantic schemas for the booking app API.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class Resource(BaseModel):
    id: int
    name: str
    shop: str
    resource_type: str


class Booking(BaseModel):
    id: int
    resource_id: int
    resource_name: str
    shop: str
    member_id: int
    member_name: str
    from_time: datetime
    to_time: datetime
    duration_hours: float


class Slot(BaseModel):
    from_time: datetime
    to_time: datetime


class MemberResult(BaseModel):
    id: int
    name: str
    email: str


class CreateBookingRequest(BaseModel):
    resource_id: int
    member_id: int
    member_name: Optional[str] = None   # for logging
    from_time: datetime
    to_time: datetime
    booked_by_id: Optional[int] = None    # set when booking on behalf of another member
    booked_by_name: Optional[str] = None
