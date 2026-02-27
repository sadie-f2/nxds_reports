# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repository contains two things:
- **`reports/`** — CLI scripts that fetch data from the [Nexudus](https://www.nexudus.com/) coworking platform API and generate reports as CSV or Excel
- **`booking-app/`** — Web app for viewing and booking resources (in development)

## Technology Stack

- **Language**: Python 3
- **Dependencies**: `requests`, `python-dotenv`, `openpyxl` (see `requirements.txt`)
- **Style**: Procedural — functions only, no classes. Progress output goes to stderr; data output (CSV) goes to stdout so reports are pipeable.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in credentials
```

## Nexudus API

Authentication supports Basic (email + password) or Bearer token. Consult Nexudus API documentation when implementing integrations. Store credentials in `.env`, never in source code.

Required env vars (see `.env.example`):

| Variable | Description |
|---|---|
| `NEXUDUS_BASE_URL` | API base URL, e.g. `https://spaces.nexudus.com/api` |
| `NEXUDUS_AUTH_TYPE` | `basic` or `bearer` |
| `NEXUDUS_EMAIL` | Email for basic auth |
| `NEXUDUS_PASSWORD` | Password for basic auth |
| `NEXUDUS_TOKEN` | Bearer token (alternative to basic auth) |
| `NEXUDUS_MOCK` | Set to `1` to use local mock data (no credentials needed) |

## Running Reports

All report scripts live in `reports/`. Run from the repo root:

```bash
# Members
NEXUDUS_MOCK=1 python reports/report_members.py
NEXUDUS_MOCK=1 python reports/report_members.py --file /tmp/members.csv
NEXUDUS_MOCK=1 python reports/report_members.py --output excel --file /tmp/members.xlsx
NEXUDUS_MOCK=1 python reports/report_members.py --active-only
python reports/report_members.py --file members.csv   # real credentials from .env

# New memberships — last 30 days (default)
NEXUDUS_MOCK=1 python reports/report_new_memberships.py
# New memberships — custom range
NEXUDUS_MOCK=1 python reports/report_new_memberships.py --from 2026-01-01 --to 2026-02-22
# New memberships — custom lookback window
NEXUDUS_MOCK=1 python reports/report_new_memberships.py --days 60

# Active memberships — flat list
NEXUDUS_MOCK=1 python reports/report_active_memberships.py
# Active memberships — summary by plan type
NEXUDUS_MOCK=1 python reports/report_active_memberships.py --summary

# Arrears — sorted by age (oldest overdue first, default)
NEXUDUS_MOCK=1 python reports/report_arrears.py
# Arrears — sorted by value (largest amount first)
NEXUDUS_MOCK=1 python reports/report_arrears.py --sort value
# Arrears — Excel output
NEXUDUS_MOCK=1 python reports/report_arrears.py --output excel --file /tmp/arrears.xlsx
```

## Project Structure

```
nexudus.py                    # Core API client (load_config, api_get, get_all, etc.)
mock_data/                    # Canned API responses for NEXUDUS_MOCK=1
requirements.txt
.env.example
reports/
  report_members.py             # Member/coworker report
  report_new_memberships.py     # New members (first-ever contract) in a date range
  report_new_contracts.py       # All new/changed contracts in a date range
  report_active_memberships.py  # Active contracts (flat list or --summary by plan type)
  report_arrears.py             # Unpaid invoices sorted by age or value
  report_bookings.py            # Equipment bookings over a time range
  report_day_passes.py          # Day pass member purchase activity
  report_left_recent.py         # Recently lapsed members (win-back list)
  report_studio_deposits.py     # Security deposits for current studio renters
  tests/                        # pytest suite
booking-app/                  # Web app for viewing and booking resources (in development)
```

## Running Tests

```bash
# Run all tests
pytest reports/tests/ -v

# With coverage (requires pytest-cov)
pytest reports/tests/ -v --cov=reports --cov-report=term-missing
```

Tests use mock data only — no credentials required.

## Coding Conventions

- **Procedural**: use module-level functions, not classes
- **stderr for progress**: all `print(..., file=sys.stderr)` for progress/errors; stdout is reserved for data output (CSV)
- **Exit on error**: API errors call `sys.exit(1)` after printing to stderr
- **Pagination**: use `nexudus.get_all()` which loops on `HasNextPage`
- **Mock mode**: check `config["mock"]` and call `nexudus._mock_response()` instead of making HTTP requests
- **New reports**: follow `reports/report_members.py` as the template — argparse → load_config → fetch → filter → output
