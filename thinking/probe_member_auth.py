"""
probe_member_auth.py — test whether Nexudus member credentials work for auth
and what scope of data they can see.

Usage:
    NEXUDUS_BASE_URL=https://spaces.nexudus.com/api \
    MEMBER_EMAIL=member@example.com \
    MEMBER_PASSWORD=theirpassword \
    python3 thinking/probe_member_auth.py

The script uses the member's own email/password (Basic auth), NOT the
admin bearer token. It checks:
  1. Can the credentials authenticate at all?
  2. What bookings does the API return — only theirs, or everyone's?
  3. Does the coworkercontracts endpoint return their record only?
"""

import os
import sys
import json
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ.get("NEXUDUS_BASE_URL", "https://spaces.nexudus.com/api").rstrip("/")
EMAIL    = os.environ.get("MEMBER_EMAIL", "").strip()
PASSWORD = os.environ.get("MEMBER_PASSWORD", "").strip()

if not EMAIL or not PASSWORD:
    print("ERROR: Set MEMBER_EMAIL and MEMBER_PASSWORD environment variables.", file=sys.stderr)
    sys.exit(1)

AUTH = (EMAIL, PASSWORD)
HEADERS = {"Accept": "application/json"}


def get(path, params=None):
    url = BASE_URL + path
    resp = requests.get(url, auth=AUTH, headers=HEADERS, params=params or {}, timeout=10)
    return resp


def report(label, resp):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"  {resp.request.method} {resp.url}")
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        try:
            data = resp.json()
            if isinstance(data, dict):
                records = data.get("Records", [])
                total   = data.get("TotalItems", "?")
                print(f"  TotalItems: {total}  |  Records in page: {len(records)}")
                if records:
                    print(f"  First record keys: {list(records[0].keys())}")
                    # Show a few identifying fields if present
                    for key in ("Id", "CoworkerId", "CoworkerFullName", "CoworkerEmail",
                                "ResourceName", "FromTime", "ToTime"):
                        if key in records[0]:
                            print(f"    [{key}] {records[0][key]}")
            else:
                print(f"  Response (non-list): {json.dumps(data)[:300]}")
        except Exception as e:
            print(f"  Could not parse JSON: {e}")
            print(f"  Body: {resp.text[:300]}")
    else:
        print(f"  Body: {resp.text[:300]}")


# --- 1. Simple auth probe: hit /userprofile or similar low-cost endpoint ---
print(f"\nProbing Nexudus as: {EMAIL}")
print(f"Base URL: {BASE_URL}")

r = get("/helpers/ping")
report("Auth probe — GET /helpers/ping", r)

# --- 2. Bookings visible under these credentials ---
from datetime import datetime, timedelta
today = datetime.utcnow()
from_dt = (today - timedelta(days=30)).strftime("%Y-%m-%dT00:00:00")
to_dt   = (today + timedelta(days=30)).strftime("%Y-%m-%dT23:59:59")

r = get("/spaces/bookings", params={
    "from_Booking_FromTime": from_dt,
    "to_Booking_FromTime":   to_dt,
})
report("Bookings visible (last 30 / next 30 days)", r)

if r.status_code == 200:
    records = r.json().get("Records", [])
    emails = {rec.get("CoworkerEmail") for rec in records if rec.get("CoworkerEmail")}
    print(f"\n  Distinct CoworkerEmails in results: {len(emails)}")
    for e in sorted(emails):
        marker = " <-- (this member)" if e and e.lower() == EMAIL.lower() else ""
        print(f"    {e}{marker}")

# --- 3. Coworker contracts visible ---
r = get("/billing/coworkercontracts", params={"CoworkerContract_Active": "true"})
report("Active contracts visible", r)

# --- 4. All coworkers/members visible ---
r = get("/spaces/coworkers")
report("Coworkers list visible", r)

print("\n" + "="*60)
print("Done.")
