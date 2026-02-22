# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repository is for Nexudus reporting — fetching data from the [Nexudus](https://www.nexudus.com/) coworking platform API and generating reports as CSV or Excel.

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

```bash
# Mock mode — no credentials needed
NEXUDUS_MOCK=1 python report_members.py

# CSV to file
NEXUDUS_MOCK=1 python report_members.py --file /tmp/members.csv

# Excel output
NEXUDUS_MOCK=1 python report_members.py --output excel --file /tmp/members.xlsx

# Active members only
NEXUDUS_MOCK=1 python report_members.py --active-only

# With real credentials (from .env)
python report_members.py --file members.csv
```

## Project Structure

```
nexudus.py           # Core API client (load_config, api_get, get_all, etc.)
report_members.py    # Member/coworker report
mock_data/           # Canned API responses for NEXUDUS_MOCK=1
requirements.txt
.env.example
```

## Coding Conventions

- **Procedural**: use module-level functions, not classes
- **stderr for progress**: all `print(..., file=sys.stderr)` for progress/errors; stdout is reserved for data output (CSV)
- **Exit on error**: API errors call `sys.exit(1)` after printing to stderr
- **Pagination**: use `nexudus.get_all()` which loops on `HasNextPage`
- **Mock mode**: check `config["mock"]` and call `nexudus._mock_response()` instead of making HTTP requests
- **New reports**: follow `report_members.py` as the template — argparse → load_config → fetch → filter → output
