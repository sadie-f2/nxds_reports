# Auth Method Evaluation

**Date:** 2026-03-02
**Context:** Booking app currently uses trust-first email verification —
`POST /api/auth/identify` takes an email, checks it against the cached
active-member list from Nexudus, and returns the member's id/name if found.
No password, no session token, no OTP.

---

## Current State (baseline)

| What happens on identify | API calls |
|---|---|
| Email submitted | Members list fetched from Nexudus (or served from 30-min cache) |
| Email matched against active contracts | — |
| Member id/name returned | — |

**Net Nexudus calls per login:** 0 if cached, 1 paginated fetch if cache cold
**Code surface:** ~30 lines in `auth.py` + `members.py`; no session state

---

## Method 1 — Nexudus Login (credential forwarding)

**How it would work:**
Member enters email + Nexudus password in the booking app. The app attempts a
Nexudus API request using Basic auth with those credentials. If Nexudus
accepts them, identity is confirmed.

The app's own API calls use a bearer token (`NEXUDUS_BOOKING_TOKEN`); this is
separate — it just tries a lightweight credentialed request (e.g. a GET to
`/spaces/me` or similar) with the member's own email/password to test validity.

### a. Code complexity

- **Auth endpoint:** Replace email-only field with email + password fields.
- **Nexudus credential probe:** New helper in `nexudus.py` that fires a
  Basic-auth request with the member's credentials and checks for 200 vs 401.
- **No session storage needed** if we stay stateless: re-verify on each
  sensitive action, or issue a short-lived app-level token (JWT or signed
  cookie) — that's significant additional surface.
- **Security smell:** The booking app handles member passwords. Members must
  trust it. Passwords travel through our server.
- **Frontend:** Password field added to login form.
**⚠️ PARTIALLY REVISED — tested + researched 2026-03-02**

Probe of the **admin API** (`/spaces/bookings`, `/billing/coworkercontracts`,
`/spaces/coworkers`) with member Basic auth → **401 on all endpoints**. The
admin API is operator-only, confirmed.

However, Nexudus also exposes a separate **Public API** that *does* accept
member email + password and returns a short-lived bearer token. Reference:
- [Get Authentication Token for User (Public API)](https://developers.nexudus.com/reference/get-authentication-token-for-user-public)
- [About the Public API](https://developers.nexudus.com/reference/about-the-public-api)

The Public API is intentionally restricted (e.g. documented as unable to
check in/out). It returns member-scoped data — likely only the authenticated
member's own bookings, not the full calendar. This means:

- Member credentials **can** be verified via the Public API auth endpoint
- But the booking app's calendar view still requires the admin API (operator
  token) — so member auth would be an additional step, not a replacement
- The booking app would need to handle member passwords — security liability
  remains

**Status: VIABLE as a credential check only — tested 2026-03-02**

Findings from `thinking/probe_public_api.py`:
- `POST https://artisans.spaces.nexudus.com/api/token` with form-encoded
  `grant_type=password&username=...&password=...` → **200, returns bearer token**
  (24h expiry) when credentials are correct; 401 when wrong.
- That member token has **zero data access** — every API endpoint returns 401.
  The "Public API" (`/en/api/public/...`) appears not enabled for this space (404).
- Upshot: the token endpoint can be used purely as a **password validator**.
  Return 200 → credentials valid. Return 401 → reject. Discard token, use admin
  credentials for all data operations as normal.

Implementation would be:
1. Member enters email + password in booking app login form
2. App POSTs to `https://{space}.spaces.nexudus.com/api/token` (form-encoded)
3. 200 → identity confirmed; 401 → reject
4. All subsequent API calls use admin token as today

Remaining concerns:
- Booking app handles member passwords (security/trust liability)
- Space subdomain (`artisans`) must be configured — add `NEXUDUS_SPACE` env var
- Members must know/remember their Nexudus portal password

---

## Method 2 — Static PIN distributed to all members

**How it would work:**
Admin runs a one-off script that generates a PIN for every active member and
emails it to them. Members use email + PIN to log in. The booking app holds a
PIN store (a JSON file or in-memory dict loaded at startup) and validates
against it.

### a. Code complexity

- **PIN generation script:** ~40–60 lines — fetch members, generate random
  PINs (e.g. 6 digits), write to a file, send emails via SMTP or Nexudus's
  messaging API.
- **PIN store:** Simple key-value file (`pins.json`: `{email: hashed_pin}`).
  Loaded at startup, no database needed.
- **Auth endpoint:** Add PIN field; compare submitted PIN against store.
- **PIN rotation:** Admin re-runs the generation script periodically (or on
  demand). Members get a new PIN by email. No real-time logic needed in the
  app.
- **No new third-party dependency** — only email sending (already common infra).
- **Frontend:** PIN field added to login form.
- **Edge cases:** New members added to Nexudus after last batch won't have
  PINs until next batch run. Need a process for that.

**Complexity delta: LOW-MEDIUM**
The app itself barely changes. Most work is in the one-off admin tooling.

### b. API call volume

| Event | Extra calls vs baseline |
|---|---|
| Login | 0 — PIN validated locally, no Nexudus call |
| Batch PIN send (one-off) | 1 member-list fetch + N email sends (infrequent) |
| Steady-state booking actions | no change |

**Volume delta: ZERO at runtime.** The batch send is admin-triggered and
infrequent (monthly or on demand). Per-login cost actually goes down because
the member-list cache is less critical (PIN validates locally).

---

## Method 3 — SMS OTP (PIN sent to phone on record)

**How it would work:**
Member enters email. App looks up their phone number in Nexudus, generates a
time-limited OTP (e.g. 6 digits, 10-min expiry), sends it via SMS gateway
(Twilio or equivalent), member enters OTP to complete login.

### a. Code complexity

- **Phone number lookup:** The current `fetch_members()` uses
  `/billing/coworkercontracts` which may not include phone. Would need a
  separate call to `/spaces/coworkers` or similar to get phone numbers.
  Nexudus phone fields are sometimes blank or unformatted — needs sanitisation.
- **SMS integration:** New dependency (Twilio SDK or HTTP client calls).
  New env vars (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`).
  New failure modes (SMS delivery failure, wrong number on file, carrier
  issues).
- **OTP store:** Time-limited in-memory dict `{email: (otp, expires_at)}`.
  Needs expiry cleanup. Works for single-process; breaks under multi-process
  without shared state (Redis, DB).
- **Two-step frontend flow:** Step 1 — submit email, trigger SMS. Step 2 —
  enter OTP. Frontend state management across steps.
- **Auth endpoint splits in two:** `POST /api/auth/request-otp` and
  `POST /api/auth/verify-otp`.
- **Members with no phone on record:** Need a fallback or blocking error.

**Complexity delta: HIGH**
Most complex of the three. New external service dependency, two-step flow,
OTP lifecycle management, phone data quality issues.

### b. API call volume

| Event | Extra calls vs baseline |
|---|---|
| Step 1 (email submit) | +1 Nexudus call for phone lookup (or piggyback on members cache if phone is included) + 1 SMS API call |
| Step 2 (OTP verify) | 0 extra (local check) |
| Booking actions | no change |

**Volume delta: +1–2 external API calls per login** (Nexudus phone lookup if
not cached; SMS gateway always). Introduces a second external service SLA
(SMS delivery latency, failure rate).

---

## Summary Table

| Criterion | Method 1 (Nexudus Login) | Method 2 (Static PIN) | Method 3 (SMS OTP) |
|---|---|---|---|
| **Code complexity** | Medium-High | Low-Medium | High |
| **API call delta (runtime)** | +1 per login | **Zero** | +1–2 per login |
| **New dependencies** | None (risk: undocumented Nexudus endpoint) | None (email infra) | SMS gateway (Twilio etc.) |
| **Handles member's password?** | Yes (security liability) | No | No |
| **Works if member has no phone?** | Yes | Yes | **No** |
| **Works offline / SMS failure?** | Yes | Yes | No |
| **Admin overhead** | None | Batch send on member changes | None |
| **UX friction** | Low (one extra field) | Low (one extra field) | High (two-step flow) |

---

## Preliminary read

**Method 2 (Static PIN)** has the best profile on both criteria: zero
steady-state API impact and minimal code change to the app itself. The main
cost is admin process (running the batch script when membership changes) and
the initial build of that script + email send.

**Method 1** is simple in concept but has the password-handling liability and
depends on Nexudus exposing a usable per-member auth probe endpoint.

**Method 3** is the most robust for security (true OTP, hard to share) but
the most expensive on all other dimensions.

---

*More implementation ideas from the user to follow — see notes below this line.*

---

## Other notes

### Production API key
Currently the booking app uses `NEXUDUS_EMAIL` + `NEXUDUS_PASSWORD` (Basic auth)
or `NEXUDUS_BOOKING_TOKEN` (Bearer). For production, cut a scoped Bearer token in
Nexudus admin and set `NEXUDUS_BOOKING_TOKEN` in the server `.env`. The token path
is already wired in `booking-app/app/nexudus.py` — no code change needed, just
config. Scoped token is preferable to admin credentials: limits blast radius if
the key leaks, and avoids storing a human password on the server.

### View-only calendar mode
Add a public "browse bookings" view that requires no login — anyone can see the
calendar but cannot make or cancel bookings. Two parts:

- **Backend:** already partially there — `BOOKING_EMAIL_GATE=0` in `.env` disables
  the identity check on page load. A dedicated read-only route (or a query param
  flag) could enforce that booking/cancel actions are blocked without identify
  being called first.
- **Frontend:** a UI state (e.g. `?readonly=1` or a toggle) that hides the booking
  form and cancel buttons, leaving the calendar visible. No new API endpoints
  needed — just a conditional render layer over the existing `/api/bookings` and
  `/api/availability` calls, which are already unauthenticated at the HTTP level.
  ┌───────────────────┬────────────────────────────────────────────────────────────────┬───────────────────────┐    
  │                   │                           Complexity                           │       API calls       │
  ├───────────────────┼────────────────────────────────────────────────────────────────┼───────────────────────┤    
  │ 1. Nexudus login  │ Medium-High — depends on whether Nexudus exposes a usable      │ +1 per login          │
  │                   │ per-member auth probe; also means the app handles passwords    │                       │
  ├───────────────────┼────────────────────────────────────────────────────────────────┼───────────────────────┤
  │ 2. Static PIN to  │ Low-Medium — app barely changes; admin script does the heavy   │ Zero at runtime       │
  │ all members       │ lifting                                                        │                       │
  ├───────────────────┼────────────────────────────────────────────────────────────────┼───────────────────────┤
  │ 3. SMS OTP        │ High — two-step frontend flow, new SMS dependency, phone data  │ +1–2 per login, new   │
  │                   │ quality issues, OTP state management                           │ external service      │
  └───────────────────┴────────────────────────────────────────────────────────────────┴───────────────────────┘

  Method 2 (Static PIN) looks strongest on both criteria — no runtime API increase and minimal code change. Method 3
   is the most secure but the most expensive everywhere. Method 1 has a password-handling liability and an unknown
  around whether Nexudus exposes a clean member-level auth endpoint.


