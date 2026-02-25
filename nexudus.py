"""
nexudus.py — Core Nexudus API client (procedural, no classes).

All progress output goes to stderr so stdout remains pipeable.
"""

import base64
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

MOCK_DATA_DIR = Path(__file__).parent / "mock_data"


def load_config():
    """Read .env / env vars, validate required keys, return config dict."""
    load_dotenv()

    mock = os.getenv("NEXUDUS_MOCK", "0").strip() == "1"
    base_url = os.getenv("NEXUDUS_BASE_URL", "").rstrip("/")
    auth_type = os.getenv("NEXUDUS_AUTH_TYPE", "basic").lower().strip()

    if not mock:
        if not base_url:
            print("ERROR: NEXUDUS_BASE_URL is not set.", file=sys.stderr)
            sys.exit(1)

        if auth_type == "basic":
            email = os.getenv("NEXUDUS_EMAIL", "")
            password = os.getenv("NEXUDUS_PASSWORD", "")
            if not email or not password:
                print(
                    "ERROR: NEXUDUS_EMAIL and NEXUDUS_PASSWORD are required for basic auth.",
                    file=sys.stderr,
                )
                sys.exit(1)
        elif auth_type == "bearer":
            token = os.getenv("NEXUDUS_TOKEN", "")
            if not token:
                print(
                    "ERROR: NEXUDUS_TOKEN is required for bearer auth.",
                    file=sys.stderr,
                )
                sys.exit(1)
        else:
            print(
                f"ERROR: Unknown NEXUDUS_AUTH_TYPE '{auth_type}'. Use 'basic' or 'bearer'.",
                file=sys.stderr,
            )
            sys.exit(1)

    return {
        "base_url": base_url,
        "auth_type": auth_type,
        "email": os.getenv("NEXUDUS_EMAIL", ""),
        "password": os.getenv("NEXUDUS_PASSWORD", ""),
        "token": os.getenv("NEXUDUS_TOKEN", ""),
        "mock": mock,
    }


def make_auth_header(config):
    """Return Authorization header dict for the configured auth type."""
    if config["auth_type"] == "basic":
        credentials = f"{config['email']}:{config['password']}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return {"Authorization": f"Basic {encoded}"}
    else:
        return {"Authorization": f"Bearer {config['token']}"}


def _mock_response(url):
    """Return canned JSON from mock_data/ when NEXUDUS_MOCK=1."""
    if "coworkercontract" in url:
        mock_file = MOCK_DATA_DIR / "coworkercontracts_page1.json"
    elif "coworkerinvoice" in url:
        mock_file = MOCK_DATA_DIR / "coworkerinvoices_page1.json"
    elif "coworkers" in url:
        mock_file = MOCK_DATA_DIR / "coworkers_page1.json"
    elif "bookings" in url:
        mock_file = MOCK_DATA_DIR / "bookings_page1.json"
    else:
        # Generic empty response for unknown endpoints
        return {
            "WasSuccessful": True,
            "Value": [],
            "HasNextPage": False,
            "CurrentPage": 1,
            "TotalPages": 1,
            "TotalItems": 0,
        }

    if not mock_file.exists():
        print(f"ERROR: Mock file not found: {mock_file}", file=sys.stderr)
        sys.exit(1)

    with open(mock_file) as f:
        return json.load(f)


def api_get(url, headers, params=None, timeout=30):
    """
    HTTP GET with a single 429 retry using Retry-After.
    Errors print to stderr and exit(1).
    """
    for attempt in range(2):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=timeout)
        except requests.RequestException as exc:
            print(f"ERROR: Request failed: {exc}", file=sys.stderr)
            sys.exit(1)

        if response.status_code == 429 and attempt == 0:
            retry_after = int(response.headers.get("Retry-After", 5))
            print(
                f"Rate limited. Retrying after {retry_after}s...",
                file=sys.stderr,
            )
            time.sleep(retry_after)
            continue

        if not response.ok:
            print(
                f"ERROR: HTTP {response.status_code} from {url}",
                file=sys.stderr,
            )
            sys.exit(1)

        return response.json()

    print(f"ERROR: Still rate limited after retry: {url}", file=sys.stderr)
    sys.exit(1)


def extract_value(response_json):
    """Unwrap Nexudus envelope.

    Real API returns {Records, HasNextPage, ...}.
    Mock data uses {WasSuccessful, Value, ...}.
    """
    if "WasSuccessful" in response_json:
        if not response_json["WasSuccessful"]:
            message = response_json.get("Message", "Unknown API error")
            print(f"ERROR: API error: {message}", file=sys.stderr)
            sys.exit(1)
        return response_json["Value"]
    return response_json.get("Records", [])


def get_page(base_url, endpoint, headers, page=1, size=100, extra_params=None):
    """Fetch one page from the API. Returns the full response dict."""
    url = base_url.rstrip("/") + "/" + endpoint.lstrip("/")
    params = {"page": page, "size": size}
    if extra_params:
        params.update(extra_params)
    return api_get(url, headers, params=params)


def get_all(base_url, endpoint, headers, size=100, extra_params=None):
    """
    Paginate through all pages using HasNextPage.
    Prints progress to stderr. Returns flat list of records.
    """
    records = []
    page = 1

    while True:
        print(f"Fetching {endpoint} page {page}...", file=sys.stderr)
        response_json = get_page(
            base_url, endpoint, headers, page=page, size=size, extra_params=extra_params
        )
        page_records = extract_value(response_json)

        if isinstance(page_records, list):
            records.extend(page_records)
        elif page_records is not None:
            records.append(page_records)

        has_next = response_json.get("HasNextPage", False)
        total = response_json.get("TotalItems", "?")
        print(
            f"  Got {len(page_records) if isinstance(page_records, list) else 1} records "
            f"(total so far: {len(records)}/{total})",
            file=sys.stderr,
        )

        if not has_next:
            break
        page += 1

    return records
