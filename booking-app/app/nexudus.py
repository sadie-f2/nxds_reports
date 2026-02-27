"""
Nexudus API adapter for the booking app.

Purpose-built for web use: raises HTTPException instead of sys.exit,
uses a limited-scope bearer token (NEXUDUS_BOOKING_TOKEN), and
supports NEXUDUS_MOCK=1 for local development.
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

import requests
from dotenv import load_dotenv
from fastapi import HTTPException

# Mock data lives at the repo root alongside the shared nexudus.py
MOCK_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "mock_data"

load_dotenv()


def _config() -> dict:
    return {
        "base_url": os.getenv("NEXUDUS_BASE_URL", "").rstrip("/"),
        "token": os.getenv("NEXUDUS_BOOKING_TOKEN", ""),
        "mock": os.getenv("NEXUDUS_MOCK", "0").strip() == "1",
    }


def _headers() -> dict:
    token = os.getenv("NEXUDUS_BOOKING_TOKEN", "")
    return {"Authorization": f"Bearer {token}"}


def _mock(url: str) -> dict:
    """Return canned JSON from mock_data/ based on URL."""
    if "resources" in url:
        path = MOCK_DATA_DIR / "resources_page1.json"
    elif "coworkercontract" in url:
        path = MOCK_DATA_DIR / "coworkercontracts_page1.json"
    elif "bookings" in url:
        path = MOCK_DATA_DIR / "bookings_page1.json"
    elif "coworkers" in url:
        path = MOCK_DATA_DIR / "coworkers_page1.json"
    else:
        return {"Records": [], "HasNextPage": False, "TotalItems": 0}

    if not path.exists():
        raise HTTPException(status_code=500, detail=f"Mock file not found: {path}")

    with open(path) as f:
        return json.load(f)


def _get(endpoint: str, params: Optional[dict] = None) -> dict:
    """GET from Nexudus, returning parsed JSON. Raises HTTPException on error."""
    cfg = _config()
    if cfg["mock"]:
        return _mock(endpoint)

    url = cfg["base_url"] + "/" + endpoint.lstrip("/")
    for attempt in range(2):
        try:
            resp = requests.get(url, headers=_headers(), params=params, timeout=30)
        except requests.RequestException as exc:
            raise HTTPException(status_code=502, detail=f"Nexudus request failed: {exc}")

        if resp.status_code == 429 and attempt == 0:
            retry_after = int(resp.headers.get("Retry-After", 5))
            time.sleep(retry_after)
            continue

        if not resp.ok:
            raise HTTPException(
                status_code=502,
                detail=f"Nexudus error {resp.status_code} from {endpoint}",
            )
        return resp.json()

    raise HTTPException(status_code=502, detail="Rate limited by Nexudus after retry")


def _records(response: dict) -> list:
    """Extract records list from Nexudus envelope."""
    if "WasSuccessful" in response:
        return response.get("Value") or []
    return response.get("Records") or []


def get_all_pages(endpoint: str, extra_params: Optional[dict] = None) -> list:
    """Fetch all pages from a paginated endpoint."""
    cfg = _config()
    if cfg["mock"]:
        return _records(_mock(endpoint))

    records = []
    page = 1
    while True:
        params = {"page": page, "size": 100}
        if extra_params:
            params.update(extra_params)
        data = _get(endpoint, params)
        records.extend(_records(data))
        if not data.get("HasNextPage", False):
            break
        page += 1
    return records


def fetch_resources() -> list[dict]:
    return get_all_pages("/spaces/resources")


def fetch_bookings(from_dt: str, to_dt: str, resource_id: Optional[int] = None) -> list[dict]:
    params: dict[str, Any] = {
        "from_Booking_FromTime": from_dt,
        "to_Booking_FromTime": to_dt,
    }
    return get_all_pages("/spaces/bookings", extra_params=params)


def fetch_members() -> list[dict]:
    """Fetch active contracts for member name/ID lookup."""
    return get_all_pages(
        "/billing/coworkercontracts",
        extra_params={"CoworkerContract_Active": "true"},
    )


def post_booking(resource_id: int, member_id: int, from_time: str, to_time: str) -> dict:
    """Create a booking. Returns the created booking record."""
    cfg = _config()
    if cfg["mock"]:
        return {
            "Id": 9999,
            "ResourceId": resource_id,
            "CoworkerId": member_id,
            "FromTime": from_time,
            "ToTime": to_time,
        }

    url = cfg["base_url"] + "/spaces/bookings"
    payload = {
        "ResourceId": resource_id,
        "CoworkerId": member_id,
        "FromTime": from_time,
        "ToTime": to_time,
    }
    try:
        resp = requests.post(url, headers=_headers(), json=payload, timeout=30)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Nexudus request failed: {exc}")

    if not resp.ok:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Nexudus booking creation failed: {resp.text}",
        )
    return resp.json()


def delete_booking(booking_id: int) -> None:
    """Cancel a booking by ID."""
    cfg = _config()
    if cfg["mock"]:
        return  # no-op in mock mode

    url = cfg["base_url"] + f"/spaces/bookings/{booking_id}"
    try:
        resp = requests.delete(url, headers=_headers(), timeout=30)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Nexudus request failed: {exc}")

    if not resp.ok:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Nexudus booking deletion failed: {resp.text}",
        )
