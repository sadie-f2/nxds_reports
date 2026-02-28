"""
Eventbrite API adapter.

Fetches events and attendance data for Artisans Asylum reporting.

Auth: private token passed as Bearer in Authorization header.
Mock: set EVENTBRITE_MOCK=1 to use local mock data (no credentials needed).

Required env vars:
    EVENTBRITE_TOKEN        — private/API token from Eventbrite developer portal
    EVENTBRITE_ORG_ID       — your Eventbrite organization ID
"""

import json
import os
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

MOCK_DATA_DIR = Path(__file__).resolve().parent.parent / "mock_data"
BASE_URL = "https://www.eventbriteapi.com/v3"

load_dotenv()


def _config() -> dict:
    return {
        "token":  os.getenv("EVENTBRITE_TOKEN", ""),
        "org_id": os.getenv("EVENTBRITE_ORG_ID", ""),
        "mock":   os.getenv("EVENTBRITE_MOCK", "0").strip() == "1",
    }


def _headers() -> dict:
    token = os.getenv("EVENTBRITE_TOKEN", "")
    return {"Authorization": f"Bearer {token}"}


def _mock_events() -> dict:
    path = MOCK_DATA_DIR / "eventbrite_events_page1.json"
    with open(path) as f:
        return json.load(f)


def _get(endpoint: str, params: Optional[dict] = None) -> dict:
    """GET from Eventbrite with one 429 retry."""
    cfg = _config()
    url = BASE_URL + endpoint
    for attempt in range(2):
        try:
            resp = requests.get(url, headers=_headers(), params=params, timeout=30)
        except requests.RequestException as exc:
            raise SystemExit(f"Eventbrite request failed: {exc}")

        if resp.status_code == 429 and attempt == 0:
            retry_after = int(resp.headers.get("Retry-After", 5))
            print(f"Rate limited — waiting {retry_after}s…", flush=True)
            time.sleep(retry_after)
            continue

        if not resp.ok:
            raise SystemExit(f"Eventbrite error {resp.status_code}: {resp.text}")

        return resp.json()

    raise SystemExit("Rate limited by Eventbrite after retry")


def fetch_events(status: str = "live") -> list[dict]:
    """
    Fetch all events for the organisation, with ticket_availability expanded.

    status: "live" | "draft" | "started" | "ended" | "completed" | "canceled" | "all"
    """
    cfg = _config()

    if cfg["mock"]:
        data = _mock_events()
        return data.get("events", [])

    if not cfg["org_id"]:
        raise SystemExit("EVENTBRITE_ORG_ID not set in .env")

    events = []
    page = 1
    while True:
        params = {
            "status": status,
            "expand": "ticket_availability",
            "page":   page,
        }
        data = _get(f"/organizations/{cfg['org_id']}/events/", params=params)
        events.extend(data.get("events", []))
        pagination = data.get("pagination", {})
        if not pagination.get("has_more_items", False):
            break
        page += 1

    return events
