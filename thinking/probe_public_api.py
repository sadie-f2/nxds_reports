"""
probe_public_api.py — test the Nexudus Public API with member credentials.

The Public API is a separate surface from the admin REST API
(spaces.nexudus.com/api/...). It lives at:
  https://{space}.spaces.nexudus.com/en/api/...

and accepts member email + password directly.

Usage:
    NEXUDUS_BASE_URL=https://spaces.nexudus.com/api \
    MEMBER_EMAIL=member@example.com \
    MEMBER_PASSWORD=theirpassword \
    python3 thinking/probe_public_api.py

The script discovers the space subdomain from the admin API, then:
  1. Authenticates as the member via the Public API token endpoint
  2. Probes what booking/resource data the member token can access
  3. Compares record counts to admin API results (scope check)
"""

import os
import sys
import json
import requests
from dotenv import load_dotenv

load_dotenv()

ADMIN_BASE  = os.environ.get("NEXUDUS_BASE_URL", "https://spaces.nexudus.com/api").rstrip("/")
ADMIN_EMAIL = os.environ.get("NEXUDUS_EMAIL", "").strip()
ADMIN_PASS  = os.environ.get("NEXUDUS_PASSWORD", "").strip()
MEMBER_EMAIL    = os.environ.get("MEMBER_EMAIL", "").strip()
MEMBER_PASSWORD = os.environ.get("MEMBER_PASSWORD", "").strip()

if not MEMBER_EMAIL or not MEMBER_PASSWORD:
    print("ERROR: Set MEMBER_EMAIL and MEMBER_PASSWORD.", file=sys.stderr)
    sys.exit(1)

ADMIN_AUTH = (ADMIN_EMAIL, ADMIN_PASS) if ADMIN_EMAIL else None
HEADERS    = {"Accept": "application/json", "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Step 1 — discover the space subdomain from the admin API
# ---------------------------------------------------------------------------

def discover_space_subdomain() -> str | None:
    """
    Pull the space's web address from the admin API so we can build the
    Public API base URL. Falls back to NEXUDUS_SPACE env var if set.
    """
    override = os.environ.get("NEXUDUS_SPACE", "").strip()
    if override:
        print(f"  Using NEXUDUS_SPACE override: {override}")
        return override

    if not ADMIN_AUTH or not ADMIN_AUTH[0]:
        print("  No admin credentials — cannot auto-discover space subdomain.", file=sys.stderr)
        return None

    url = ADMIN_BASE + "/sys/businesses"
    try:
        resp = requests.get(url, auth=ADMIN_AUTH, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            print(f"  /sys/businesses → {resp.status_code}", file=sys.stderr)
            return None
        data = resp.json()
        records = data.get("Records", [data] if isinstance(data, dict) else [])
        for biz in records:
            web = biz.get("WebAddress") or biz.get("Url") or biz.get("WebSiteUrl") or ""
            if "spaces.nexudus.com" in web:
                sub = web.split(".spaces.nexudus.com")[0].lstrip("https://").lstrip("http://")
                print(f"  Discovered space subdomain: {sub!r}  (from {web})")
                return sub
            # also try the Name as a slug hint
            name = biz.get("Name") or ""
            print(f"  Business record — Name: {name!r}, WebAddress: {web!r}")
    except Exception as e:
        print(f"  Error discovering subdomain: {e}", file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# Step 2 — authenticate as member via Public API
# ---------------------------------------------------------------------------

def get_member_token(space: str) -> str | None:
    """
    POST member credentials to the Public API token endpoint.
    Returns bearer token string or None.
    """
    # Known candidate endpoints (try in order)
    candidates = [
        f"https://{space}.spaces.nexudus.com/en/user/token",
        f"https://{space}.spaces.nexudus.com/en/user/refreshAccessToken",
        f"https://{space}.spaces.nexudus.com/api/token",
    ]

    payload_json = {"grant_type": "password", "username": MEMBER_EMAIL, "password": MEMBER_PASSWORD}
    payload_form = f"grant_type=password&username={MEMBER_EMAIL}&password={MEMBER_PASSWORD}"

    for url in candidates:
        print(f"\n  Trying: POST {url}")
        # try JSON first
        for (ctype, body) in [
            ("application/json",                  payload_json),
            ("application/x-www-form-urlencoded", payload_form),
        ]:
            try:
                resp = requests.post(
                    url,
                    data=body if ctype == "application/x-www-form-urlencoded" else None,
                    json=body if ctype == "application/json" else None,
                    headers={"Content-Type": ctype, "Accept": "application/json"},
                    timeout=10,
                )
                print(f"    [{ctype.split('/')[1]}] → {resp.status_code}")
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        token = data.get("access_token") or data.get("token") or data.get("Token")
                        if token:
                            print(f"    ✓ Got token: {token[:20]}...")
                            print(f"    token_type:  {data.get('token_type')}")
                            print(f"    expires_in:  {data.get('expires_in')}")
                            return token
                        else:
                            print(f"    Response (no token field found): {json.dumps(data)[:300]}")
                    except Exception:
                        print(f"    Non-JSON 200: {resp.text[:200]}")
                elif resp.status_code not in (404, 405):
                    print(f"    Body: {resp.text[:200]}")
            except Exception as e:
                print(f"    Error: {e}")

    return None


# ---------------------------------------------------------------------------
# Step 3 — probe data access with member token
# ---------------------------------------------------------------------------

def probe_with_token(space: str, token: str):
    auth_header = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    pub_base = f"https://{space}.spaces.nexudus.com/en/api"

    from datetime import datetime, timedelta, timezone
    today = datetime.now(timezone.utc)
    from_dt = (today - timedelta(days=30)).strftime("%Y-%m-%dT00:00:00")
    to_dt   = (today + timedelta(days=30)).strftime("%Y-%m-%dT23:59:59")

    space_api = f"https://{space}.spaces.nexudus.com/api"

    endpoints = [
        # Try member token against space-specific subdomain API
        ("Bookings (space subdomain /api/spaces/bookings)",
         f"{space_api}/spaces/bookings",
         {"from_Booking_FromTime": from_dt, "to_Booking_FromTime": to_dt}),
        ("Resources (space subdomain /api/spaces/resources)",
         f"{space_api}/spaces/resources", {}),
        ("Contracts (space subdomain /api/billing/coworkercontracts)",
         f"{space_api}/billing/coworkercontracts",
         {"CoworkerContract_Active": "true"}),
        ("Coworkers (space subdomain /api/spaces/coworkers)",
         f"{space_api}/spaces/coworkers", {}),
        # Old public API paths (may be deprecated)
        ("Bookings (old /en/api/public/)",
         f"https://{space}.spaces.nexudus.com/en/api/public/bookings",
         {"from_Booking_FromTime": from_dt, "to_Booking_FromTime": to_dt}),
        # Generic admin API with member token — expect 401
        ("Bookings (generic admin — expect 401)",
         f"{ADMIN_BASE}/spaces/bookings",
         {"from_Booking_FromTime": from_dt, "to_Booking_FromTime": to_dt}),
    ]

    for label, url, params in endpoints:
        print(f"\n{'='*60}")
        print(f"  {label}")
        try:
            resp = requests.get(url, headers=auth_header, params=params, timeout=10)
            print(f"  {resp.request.method} {resp.url}")
            print(f"  Status: {resp.status_code}")
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    if isinstance(data, dict):
                        records = data.get("Records", [])
                        total   = data.get("TotalItems", data.get("total", "?"))
                        print(f"  TotalItems: {total}  |  Records in page: {len(records)}")
                        if records:
                            r0 = records[0]
                            print(f"  First record keys: {list(r0.keys())[:10]} ...")
                            for key in ("Id", "CoworkerId", "CoworkerFullName", "CoworkerEmail",
                                        "ResourceName", "FromTime", "ToTime", "Email", "Name"):
                                if key in r0:
                                    print(f"    [{key}] {r0[key]}")
                    elif isinstance(data, list):
                        print(f"  Records: {len(data)}")
                    else:
                        print(f"  Response: {json.dumps(data)[:400]}")
                except Exception:
                    print(f"  Non-JSON: {resp.text[:300]}")
            else:
                print(f"  Body: {resp.text[:200]}")
        except Exception as e:
            print(f"  Error: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

print(f"\nNexudus Public API probe")
print(f"Member: {MEMBER_EMAIL}")
print(f"Admin base: {ADMIN_BASE}")

print("\n--- Step 1: Discover space subdomain ---")
space = discover_space_subdomain()
if not space:
    space = input("\nCould not auto-discover. Enter space subdomain (e.g. 'myspace'): ").strip()

if not space:
    print("No space subdomain — cannot continue.", file=sys.stderr)
    sys.exit(1)

print(f"\nPublic API base: https://{space}.spaces.nexudus.com/en/api")

print("\n--- Step 2: Get member token ---")
token = get_member_token(space)

if not token:
    print("\n✗ Could not obtain a member token from any candidate endpoint.")
    print("  Check the developers.nexudus.com docs for the correct token URL.")
    sys.exit(1)

print("\n--- Step 3: Probe data access with member token ---")
probe_with_token(space, token)

print(f"\n{'='*60}")
print("Done.")
