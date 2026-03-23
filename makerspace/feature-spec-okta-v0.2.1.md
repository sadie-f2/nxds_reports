# Makerspace Management Platform — Feature Spec (Okta) v0.2.1

## Overview

A web application to replace Nexudus as the management platform for a makerspace
with 500 members, growing toward 1,000. Nexudus is designed for co-working and
handles makerspace workflows poorly — specifically tool/equipment booking visibility,
certification management, and reporting flexibility.

### Goals
- Self-service member portal with clear booking availability
- Membership and billing management via Stripe
- Equipment certification tracking (trust-enforced, not hardware-gated)
- Lightweight day-pass flow using physical fobs
- Flexible reporting
- Maintainable by minimal technical staff after initial build
- Member lifecycle automation via Okta Workflows (reducing staff overhead)

### Non-Goals (Phase 2 — Classes Module)
- Eventbrite integration for class listings
- Auto-certification from class attendance
- Class scheduling and management

**Note:** The Eventbrite/Classes module may be built as a standalone application
ahead of the core platform and integrated once both exist. The integration seam
(certifications table) is defined in this spec. If the standalone module is ready
before Phase 2 begins, it may be pulled into core scope.

---

## Technology Stack

| Layer | Choice |
|---|---|
| Framework | Next.js 14+ (App Router, TypeScript) |
| Database | PostgreSQL |
| ORM | Prisma |
| Identity | Okta (non-profit pricing; free for first 50 users) |
| Billing | Stripe |
| Hosting | Railway or Render (~$80–100/month) |

---

## Budget

| Item | Cost |
|---|---|
| Initial development | $8,000 |
| Hosting | ~$1,000/year |
| Okta (500 members + Brivo Identity Connector + sandbox) | ~$14,000/year |
| Buffer (maintenance, surprises) | ~$1,500/year |
| **Total annual operating** | ~$16,500/year |

**Build phase cost:** Okta is free for the first 50 users. The full $14,000/year
spend does not begin until rollout to the full membership at go-live. The entire
build and validation phase runs at zero identity cost.

Programmer: 6 months dedicated, gifted to the organisation.

**Context:** ~$16,500/year is approximately 50% below typical IT spend for an
organisation of this size, while replacing a system (Nexudus) that generates
significant staff overhead in manual business processes.

---

## External Integrations

### Okta (identity and directory)

Okta serves as the single source of truth for member identity across all systems.

- Universal Directory: member records, groups (membership tiers), attributes
- SSO for the makerspace application and Nexudus (Nexudus is configured to
  authenticate against Okta)
- Brivo provisioning/deprovisioning via the Brivo Identity Connector (included
  in the $14,000/year quote — no custom Brivo API code required)
- Okta Workflows: member lifecycle automation (see Workflows section)
- Non-profit pricing; free for first 50 users during build and validation phase
- Sandbox environment included for ongoing development and maintenance

### Brivo (building access)

Brivo controls building entry for all members. Provisioning is handled entirely
by the Okta → Brivo Identity Connector. No custom Brivo API integration is required.

**What Brivo is used for:**
- Building access for all active members
- Deprovisioning access automatically when membership lapses (via Okta)

**What Brivo is NOT used for:**
- Shop or tool physical access — trust-enforced within the app only
- Day-pass access — handled via physical fobs (see Day-Pass section)

### Stripe
- Recurring subscriptions for membership tiers
- Monthly add-ons for studio and storage rentals
- One-time payments for day passes
- Non-profit pricing applies
- Stripe events trigger Okta Workflows for member lifecycle changes (native
  Stripe connector or HTTP bridge — to be confirmed with Okta)

---

## Okta Workflows

Okta Workflows handles member lifecycle automation, replacing custom application
code for these operations. Flows are built in Okta's no-code environment.

### Planned Flows

- **Member onboarding**: new member created in Okta → assign to tier group →
  Brivo access provisioned automatically
- **Member offboarding**: membership lapses or cancelled → Brivo access revoked →
  account suspended
- **Tier change**: membership tier updated → group membership updated →
  Brivo access groups updated
- **Payment failure**: Stripe payment fails → member status updated →
  access suspended after grace period
- **Additional flows** TBD based on operational requirements

### Stripe Integration

Stripe events (new subscription, cancellation, payment failure) need to trigger
Workflows. Okta has a native Stripe connector in the Workflows marketplace —
confirm availability before build starts. Fallback: the application receives
Stripe webhooks and calls an Okta Workflows HTTP trigger endpoint.

---

## Build and Validation Phase

Before full membership rollout, the complete stack is built and validated against
a cohort of up to 50 users (staff and key volunteers) at zero Okta cost.

**Advantages of this approach:**
- Real-world validation with users who can tolerate rough edges
- Staff and volunteers use the booking calendar daily — real edge cases surface
- Nexudus remains live for the full membership during this period; no risk
- Full $14,000/year Okta spend deferred until go-live confidence is established
- Okta configuration, Workflows, Brivo connector, and app all proven before
  the full membership is affected

---

## Membership

### Tiers

Membership tiers are configurable — the system must support adding new tiers and
defining their permissions without code changes. Tiers are implemented as Okta
groups; the application reads group membership to determine access rules.

| Property | Standard tiers | 24/7 tier |
|---|---|---|
| Studio rental eligible | No | Yes |
| Storage rental eligible | Yes | Yes |
| Tool booking | Yes (with certification) | Yes (with certification) |
| Building access | Yes | Yes |

The 24/7 tier is the only tier eligible for studio rental. The facility operates
24/7; there is no hours-based access distinction between tiers at this time,
though the system should support configurable access hours for other deployments.

### Day-Pass Members

Day passes use a pool of physical fobs (currently 12). A member purchasing a day
pass is given a fob at the facility for the duration of their visit and returns
it on departure. The fob may be associated with the member's known permissions
for the period it is active.

- Purchase a day pass online (Stripe one-time payment) or at the facility
- Staff assign a fob from the pool
- Fob returned on departure
- No Okta provisioning required; no Brivo API interaction required
- Day-pass members are not carried in Nexudus (avoids per-member cost)
- Booking policy for day-pass members: TBD (likely meeting rooms only)

---

## Billing (Stripe)

### Subscription Structure
Each active member has a Stripe subscription consisting of:
- **Base product**: membership tier (monthly recurring)
- **Studio add-on**: monthly, if a studio is assigned (24/7 tier only)
- **Storage add-on**: monthly, if a storage unit is assigned (any tier)

### Day Passes
- One-time Stripe payment
- No automated provisioning required (physical fob model)

### Billing Rules
- Studio and storage charges are added when assignments are created by an admin
- Assignment start: charge is prorated from the start date to end of month
- Assignment end: always effective at end of the current billing month
- Stripe handles proration on start; end-of-month logic is enforced by the app

---

## Studio Management

Studios are rented monthly by 24/7-tier members. Average tenancy is 1+ year.

### Data Model
- Studio inventory (name, description, size, monthly rate)
- Assignment: studio → member, start date, end date (nullable)

### Admin Workflows
- Assign studio to eligible member → Stripe add-on created automatically
- End assignment (effective end of month) → Stripe add-on removed automatically
- View all studios: occupied / vacant

### Member Portal
- Member can see their assigned studio and current monthly charge

---

## Storage Management

Storage units are rented monthly by any active member. Average tenancy is 9+ months.

### Data Model
- Storage unit inventory (identifier, monthly rate)
- Assignment: unit → member, start date, end date (nullable)

### Admin Workflows
- Assign unit to member → Stripe add-on created automatically
- End assignment (effective end of month) → Stripe add-on removed automatically
- View all units: occupied / vacant

### Member Portal
- Member can see their assigned unit(s) and current monthly charge

---

## Certification Management

Most tools require certification before a member may book them. Certification is
trust-enforced within the app — there is no hardware access gate on shop doors.

### Data Model
- Equipment classes (e.g. Laser, CNC, Woodshop, Metal Shop)
- Member certifications: member → equipment class → certified\_on date

### Admin Workflows
- Grant certification to a member for an equipment class
- Revoke certification
- View all certifications for a member
- View all certified members for an equipment class

### Member Portal
- Member can view their own certifications
- Member can view certifications held by other members (no compelling privacy
  reason to restrict this; supports coordination between members)

---

## Booking Calendar

Members can book tools, meeting rooms, and whole shops. The core UX requirement
is that members can clearly see what is already booked before attempting to reserve.

The booking-app (in the nxds_reports project) provides a working implementation
of the calendar view and booking flow against the Nexudus API. That design and
logic carries forward into this system.

The facility is 24/7. Availability is purely interval arithmetic on existing
bookings — no operating hours logic required for this deployment. The system
should support configurable operating hours for other deployments.

### Resource Types

**Tools**
- Belong to a shop
- Require a specific equipment class certification to book
- No limit on the number of tools per shop

**Meeting Rooms**
- No certification requirement
- Available to all active members

**Shops (whole-space)**
- Bookable as a unit (e.g. for an event or dedicated session)
- No certification requirement to book the whole shop

### Booking Rules
- Member must hold the required certification to book a tool
- Day-pass members: booking policy TBD (likely meeting rooms only)
- Double-booking prevented by the system
- Bookings are visible to all members, including who has booked a resource

### Member Workflows
- Browse availability calendar across all resource types
- Create a booking (with certification check where required)
- Cancel a booking
- View upcoming bookings

### Admin Workflows
- View all bookings
- Cancel any booking
- Manage resource inventory (add/edit tools, rooms, shops)
- Assign tools to shops and equipment classes

---

## Member Portal

Self-service portal for authenticated members (via Okta SSO).

### Sections
- **Dashboard**: membership status, upcoming bookings, quick links
- **Membership**: tier, billing summary, payment history
- **Bookings**: calendar view, create/cancel bookings
- **Certifications**: own certifications; member directory of certifications
- **Studio / Storage**: current assignments and monthly charges
- **Profile**: contact details, password (via Okta)

---

## Admin Dashboard

Internal tool for staff.

### Sections
- **Members**: list, search, view/edit member details, change tier
- **Studios**: inventory, current assignments, assign/end
- **Storage**: inventory, current assignments, assign/end
- **Certifications**: grant/revoke per member
- **Resources**: manage tools, rooms, shops; assign tools to shops/classes
- **Bookings**: view all, cancel
- **Day Passes**: view issued passes, fob pool status
- **Reporting**: see Reporting section

---

## Reporting

Flexible reporting was a primary Nexudus pain point. Core reports:

- **Membership by tier**: current count per tier, trend over time
- **Revenue summary**: recurring MRR, add-ons, day pass income
- **Studio occupancy**: occupied vs. vacant, revenue per studio
- **Storage occupancy**: occupied vs. vacant, revenue
- **Booking utilisation**: bookings per resource, peak times
- **Certifications**: members certified per equipment class
- **Day pass volume**: passes sold per day/week/month

Reports exportable as CSV.

---

## Accessibility

The application will be built to a basic accessibility standard:
- Semantic HTML throughout
- Keyboard navigability
- Sufficient colour contrast

A formal post-build accessibility review will be conducted by an expert screen
reader user before general rollout. Findings are expected to be surgical
(labels, focus order, alt text) rather than structural, given the baseline
approach. No formal WCAG compliance audit is planned.

---

## Data Migration (Nexudus)

### Identity migration

Near-zero. Nexudus is configured to authenticate against Okta from the start of
the project. Members log in via Okta credentials throughout the transition. At
cutover, the new application simply becomes the destination — no member identity
data needs to be moved.

### Data migration (one-time at cutover)

- Certifications
- Active studio and storage assignments
- Bookable resource inventory (tools, rooms, shops)
- Member profiles (name, contact details, tier assignment)

Historical billing data remains in Nexudus for reference; not migrated.

### Post-cutover safety net

Nexudus will be kept accessible (all members set to inactive) for a period
post-cutover. Inactive members incur no per-member charge; base plan cost is
~$150/month. Reactivation is available if the new system experiences a critical
failure.

---

## Out of Scope — Phase 2: Classes Module

Classes are the second revenue arm. Billing is handled entirely by Eventbrite and
will not be replaced. The Classes Module is a separate, independent application
that integrates with the core system via the certifications table.

The module may be built ahead of the core platform as a standalone tool. If so,
integration into the member portal can be pulled into Phase 1 scope.

### Planned Phase 2 Features
- Display upcoming classes from Eventbrite API in the member portal
- Eventbrite webhook → auto-grant certification on class completion
- (Later) create and manage Eventbrite events from within the app

---

## Identity Provider Abstraction

The application will be built for potential future portability to other identity
providers (Auth0, or others) and eventual open source release.

**Rule:** Business logic must not couple to Okta-specific APIs. All Okta
interactions are isolated in a thin adapter layer. Application code calls the
adapter; it does not call Okta directly.

This means:
- User lookup, group membership checks, and profile reads go through the adapter
- Okta Workflows automation is a deployment-specific concern, not baked into
  application flow logic — the app behaves correctly if a lifecycle event is
  handled by a Workflow or by application code
- Swapping the identity provider in a future deployment (Auth0, or others) is a
  contained change to the adapter layer, not a rewrite

**Future variants this enables:**
- Auth0-backed deployment (near-identical OIDC flow; Auth0 equivalents for
  admin API calls; application-level code replaces Workflows automation)
- Open source release for other makerspaces — internationalization, installation
  tooling, and configuration support are out of scope for this build but the
  abstraction approach keeps that path open

---

## DevOps and Environments

### Environments

Three environments: **development**, **staging**, **production**.

### Shared Development Host

A high-spec workstation running Ubuntu serves as the shared development and build
environment. All developers SSH into this machine; Claude coding sessions run
there as well. This is the primary mechanism for identical development environments
— one filesystem, one PostgreSQL instance, no per-developer environment drift.

The same host serves as the staging environment for integration testing before
production deploys.

If any developers are remote, the workstation requires network accessibility
(WireGuard VPN recommended).

### PostgreSQL Version

**PostgreSQL 16** throughout all environments, matching the existing host:
`PostgreSQL 16.13 (Ubuntu 16.13-0ubuntu0.24.04.1)`. DigitalOcean Managed
PostgreSQL supports 14–16; production will run 16.

### Environment Summary

| Environment | Infrastructure | Database | Purpose |
|---|---|---|---|
| Development / Staging | Shared Ubuntu workstation | PostgreSQL 16 (local) | Active development and integration testing |
| Production | Railway or Render (TBD) | DigitalOcean Managed PostgreSQL 16 | Live system |

### Source Control

GitHub, new repository. Organisation TBD.

### CI/CD

Pipeline tooling deferred to lead developer's preference. GitHub Actions is the
default assumption. At minimum, CI should run on pull requests:
- Type checking (`tsc --noEmit`)
- Linting
- Unit and integration tests
- Prisma schema validation

Deployment to staging and production via CI on merge to respective branches.

### Secrets Management

Approach TBD after hosting platform is confirmed. No secrets in the repository.
Environment variables via hosting platform's secrets UI for staging/production;
`.env.local` (gitignored) for local development.

### Open Decisions

- [ ] Railway vs Render for production hosting (lead developer's call)
- [ ] CI/CD pipeline tooling (lead developer's call)
- [ ] Staging host: idle workstation vs 2GB cloud instance
- [ ] Secrets management approach (after hosting confirmed)
- [ ] Remote developer access to staging workstation (VPN vs other)

---

## Future: Solid Project / Data Sovereignty (v1.1–1.4)

The Solid Project (solidproject.org) enables member data sovereignty — member profile
data resides in the member's own personal data pod rather than the application's
database. The application requests access to read/write pod data with the member's
consent. Members own their data: it is portable and revocable.

This is a planned future feature, not v1.0 scope. Three design decisions made in
v1.0 keep this path open at low cost.

### What Belongs in Pods vs the Application Database

| Data | Pod | App DB |
|---|---|---|
| Member profile (name, contact info) | ✅ natural fit | |
| Certifications | ✅ portable to other makerspaces | |
| Membership tier / billing | | ✅ Stripe is source of truth |
| Bookings | | ✅ makerspace owns these |
| Studio / storage assignments | | ✅ app-owned |

Certifications as portable verifiable credentials are particularly compelling —
a member's qualifications travel with them to any participating makerspace.

### v1.0 Design Constraints (Keep the Door Open)

**1. Data abstraction layer for member data**
Member profile reads and writes go through an interface, not direct Prisma calls.
Pod-enabled members resolve profile data from their pod; non-pod members resolve
from the application database. This abstraction must be designed in from the start —
retrofitting it across the codebase is expensive.

**2. WebID field on member records**
Member records include a `webId` field (a URI identifying the member's Solid
identity) alongside the Okta user ID. One column; negligible cost at schema
design time.

**3. RDF-friendly schema naming**
Field names align to established ontologies where practical (vCard for contact
data, schema.org for general properties). Reduces translation friction when
mapping to RDF at implementation time.

### Authentication Consideration

Solid uses WebID-OIDC — a Solid-specific extension of OIDC. Bridging this with
Okta is not a solved configuration problem. Inrupt (the primary Solid company)
has done work on OIDC provider compatibility, but a clean Okta bridge requires
investigation before v1.1 design begins. This is the key open question for the
Solid roadmap and may influence the long-term identity provider choice for
open-source variants of this application.

### Phased Implementation (v1.1–1.4)

- **v1.1**: Optional pod storage for member profiles; WebID login alongside standard auth
- **v1.2**: Certifications as Solid verifiable credentials
- **v1.3**: Member-controlled data sharing preferences
- **v1.4**: Cross-makerspace certification portability

---

## Open Questions

- [ ] Confirm Stripe is a supported Okta Workflows trigger (native connector or HTTP bridge)
- [ ] Day-pass booking policy: meeting rooms only, or tools also?
- [ ] Membership tier names and exact monthly rates
- [ ] Studio and storage unit inventory counts
- [ ] Equipment class list and which tools require which class
- [ ] Data export format available from Nexudus for migration
- [ ] Fob pool management: how are fobs tracked, what happens if one is lost?
- [ ] Confirm Okta pricing at 700 and 1,000 members
- [ ] WebID-OIDC / Okta bridge viability for Solid v1.1 roadmap

---

## Effort Estimation

### Basis

Estimates are for a Claude (AI) + human programmer pairing. Claude handles the
bulk of code generation; the human handles review, decisions, real-environment
validation, and testing against live sandboxes.

### Phase Breakdown

| Phase | Estimate |
|---|---|
| Schema + core models | 2–4 days |
| Okta integration (OIDC, user/group sync) | 1 day |
| Okta Workflows (member lifecycle flows) | 3–5 days |
| Stripe billing + webhooks | 1–1.5 weeks |
| Stripe → Okta bridge (if native connector unavailable) | 1–2 days |
| Booking calendar | 1.5–2.5 weeks |
| Member portal + admin dashboard | 1–2 weeks |
| Certifications + studio/storage | 4–7 days |
| Reporting | 2–4 days |
| Migration tooling | 1–1.5 weeks |
| Testing, QA, deployment | 2–3 weeks |
| **Total** | **8–13 weeks** |

### Range Notes

- **Low end (8 weeks):** Clean Nexudus data export, Stripe Workflows connector
  confirmed, scope holds firm
- **High end (13 weeks):** More realistic — Stripe bridge needed, migration data
  requires cleaning, sandbox-vs-production surprises

### Remaining Schedule Risks

- Stripe → Okta Workflows integration (native vs bridge)
- Nexudus data export quality (unknown until requested)
- Stripe subscription add-on edge cases (proration, failed payments)

### Model Split

Roughly 30% Opus (complex design sessions: data model, Stripe webhook logic,
booking conflict engine, Workflows design) and 70% Sonnet (straightforward
implementation work).
