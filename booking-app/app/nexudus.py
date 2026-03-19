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

# In-memory store for bookings created during mock mode. Seeded from the
# static JSON file on first access, then kept in memory so new bookings
# appear immediately without restarting the server.
_mock_bookings: list[dict] | None = None
_mock_next_id: int = 9000


def _get_mock_bookings() -> list[dict]:
    global _mock_bookings
    if _mock_bookings is None:
        path = MOCK_DATA_DIR / "bookings_page1.json"
        with open(path) as f:
            _mock_bookings = json.load(f).get("Records", [])
    return _mock_bookings


def _config() -> dict:
    return {
        "base_url": os.getenv("NEXUDUS_BASE_URL", "").rstrip("/"),
        "token": os.getenv("NEXUDUS_BOOKING_TOKEN", ""),
        "mock": os.getenv("NEXUDUS_MOCK", "0").strip() == "1",
    }


def _auth_kwargs() -> dict:
    """Return requests kwargs for auth — bearer token if set, else basic auth."""
    token = os.getenv("NEXUDUS_BOOKING_TOKEN", "")
    if token:
        return {"headers": {"Authorization": f"Bearer {token}"}}
    return {"auth": (os.getenv("NEXUDUS_EMAIL", ""), os.getenv("NEXUDUS_PASSWORD", ""))}


def _mock(url: str) -> dict:
    """Return canned JSON from mock_data/ based on URL."""
    if "resources" in url:
        path = MOCK_DATA_DIR / "resources_page1.json"
        if not path.exists():
            raise HTTPException(status_code=500, detail=f"Mock file not found: {path}")
        with open(path) as f:
            return json.load(f)
    elif "bookings" in url:
        records = _get_mock_bookings()
        return {"Records": records, "HasNextPage": False, "TotalItems": len(records)}
    elif "coworkercontract" in url:
        path = MOCK_DATA_DIR / "coworkercontracts_page1.json"
        if not path.exists():
            raise HTTPException(status_code=500, detail=f"Mock file not found: {path}")
        with open(path) as f:
            return json.load(f)
    elif "coworkers" in url:
        path = MOCK_DATA_DIR / "coworkers_page1.json"
        if not path.exists():
            raise HTTPException(status_code=500, detail=f"Mock file not found: {path}")
        with open(path) as f:
            return json.load(f)
    else:
        return {"Records": [], "HasNextPage": False, "TotalItems": 0}


def _request(method: str, url: str, **kwargs) -> requests.Response:
    """Make an HTTP request with one 429 retry. Raises HTTPException on failure."""
    auth = _auth_kwargs()
    for attempt in range(2):
        try:
            resp = requests.request(method, url, timeout=30, **auth, **kwargs)
        except requests.RequestException as exc:
            raise HTTPException(status_code=502, detail=f"Nexudus request failed: {exc}")

        if resp.status_code == 429 and attempt == 0:
            retry_after = int(resp.headers.get("Retry-After", 5))
            time.sleep(retry_after)
            continue

        return resp

    raise HTTPException(status_code=502, detail="Rate limited by Nexudus after retry")


def _get(endpoint: str, params: Optional[dict] = None) -> dict:
    """GET from Nexudus, returning parsed JSON. Raises HTTPException on error."""
    cfg = _config()
    if cfg["mock"]:
        return _mock(endpoint)

    url = cfg["base_url"] + "/" + endpoint.lstrip("/")
    resp = _request("GET", url, params=params)
    if not resp.ok:
        raise HTTPException(status_code=502, detail=f"Nexudus error {resp.status_code} from {endpoint}")
    return resp.json()


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


def verify_member_password(email: str, password: str) -> bool:
    """
    Verify a member's Nexudus password via the space token endpoint.
    Returns True if credentials are valid, False otherwise.
    In mock mode always returns True.
    """
    cfg = _config()
    if cfg["mock"]:
        return True

    space = os.getenv("NEXUDUS_SPACE", "").strip()
    if not space:
        raise HTTPException(status_code=500, detail="NEXUDUS_SPACE not configured.")

    url = f"https://{space}.spaces.nexudus.com/api/token"
    try:
        resp = requests.post(
            url,
            data=f"grant_type=password&username={requests.utils.quote(email)}&password={requests.utils.quote(password)}",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Nexudus auth check failed: {exc}")

    return resp.status_code == 200


def fetch_members() -> list[dict]:
    """Fetch active contracts for member name/ID lookup."""
    return get_all_pages(
        "/billing/coworkercontracts",
        extra_params={"CoworkerContract_Active": "true"},
    )


def post_booking(resource_id: int, member_id: int, from_time: str, to_time: str, notes: str = "") -> dict:
    """Create a booking. Returns the created booking record."""
    global _mock_next_id
    cfg = _config()
    if cfg["mock"]:
        # Look up member name from mock contracts
        contracts = _records(_mock("coworkercontract"))
        member_name = next(
            (c.get("CoworkerFullName", "") for c in contracts if c.get("CoworkerId") == member_id),
            f"Member {member_id}",
        )
        # Look up resource name from mock resources
        resources = _records(_mock("resources"))
        resource_name = next(
            (r.get("Name", "") for r in resources if r.get("Id") == resource_id),
            f"Resource {resource_id}",
        )
        record = {
            "Id": _mock_next_id,
            "BookingNumber": _mock_next_id,
            "ResourceId": resource_id,
            "ResourceName": resource_name,
            "CoworkerId": member_id,
            "CoworkerFullName": member_name,
            "FromTime": from_time,
            "ToTime": to_time,
            "Notes": notes,
        }
        _mock_next_id += 1
        _get_mock_bookings().append(record)
        return record

    url = cfg["base_url"] + "/spaces/bookings"
    payload = {
        "ResourceId": resource_id,
        "CoworkerId": member_id,
        "FromTime": from_time,
        "ToTime": to_time,
        "Notes": notes,
    }
    resp = _request("POST", url, json=payload)
    if not resp.ok:
        raise HTTPException(status_code=resp.status_code, detail=f"Nexudus booking creation failed: {resp.text}")
    data = resp.json()
    if not data.get("WasSuccessful", True):
        raise HTTPException(status_code=400, detail=f"Nexudus booking creation failed: {resp.text}")
    # Nexudus wraps the created record in {"WasSuccessful": true, "Value": {...}}
    return data.get("Value") or data


def delete_booking(booking_id: int) -> None:
    """Cancel a booking by ID."""
    cfg = _config()
    if cfg["mock"]:
        bookings = _get_mock_bookings()
        to_remove = [b for b in bookings if b.get("Id") == booking_id]
        for b in to_remove:
            bookings.remove(b)
        return

    url = cfg["base_url"] + f"/spaces/bookings/{booking_id}"
    resp = _request("DELETE", url)
    if not resp.ok:
        raise HTTPException(status_code=resp.status_code, detail=f"Nexudus booking deletion failed: {resp.text}")
