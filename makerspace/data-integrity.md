# Data Integrity, Audit & Recovery — Spec v1.0

## Motivation

Nexudus has no audit trail and no rollback capability. Deleting a "team" silently cascades
to delete all associated contracts — with no recovery option. This document defines the
data integrity posture for the makerspace platform so that no accidental or erroneous action
is unrecoverable.

---

## Principles

1. **Nothing is permanently gone.** Deletions are soft. Data is never hard-deleted in normal
   operation.
2. **Every action is recorded.** All mutations — by any user, at any layer — write an audit
   log entry.
3. **External side effects are flagged, not silently swallowed.** When an undo or rollback
   cannot automatically reverse a downstream effect (Stripe, Brivo), the UI says so explicitly.
4. **Recovery is possible without a DBA.** Staff should be able to reverse most mistakes
   through the admin UI without direct database access.
5. **When in doubt, freeze.** A write-lock mechanism lets staff halt all mutations while
   assessing or recovering from a data problem.

---

## Soft Deletes

All entities that carry meaningful state are soft-deleted:

- Members
- Memberships / tier assignments
- Studio and storage assignments
- Certifications
- Bookings
- Resources (tools, rooms, shops)
- Day pass records

**Implementation:** every such table carries `deleted_at TIMESTAMP` and `deleted_by UUID`.
All application queries filter `WHERE deleted_at IS NULL` by default. Deleted records remain
fully queryable via admin tools and the audit system.

Hard deletes are never issued by application code in normal operation. A hard-delete requires
direct database access and is a deliberate, out-of-band act.

### Cascade guard

Before any delete that has downstream soft-deleteable children, the application counts
affected records and requires explicit acknowledgment:

> "Deleting group 'Workshop Crew' will soft-delete 47 associated records. Confirm?"

Silent cascades are not permitted.

---

## Audit Log

A single append-only table records every state-changing action across the platform.

```prisma
model AuditLog {
  id          String   @id @default(cuid())
  timestamp   DateTime @default(now())
  actorId     String?                        // null = system/webhook
  actorType   String                         // "member", "admin", "system"
  action      String                         // "create", "update", "delete", "restore"
  entityType  String                         // "Member", "Booking", "Assignment", etc.
  entityId    String
  before      Json?                          // full record snapshot before change
  after       Json?                          // full record snapshot after change
  note        String?                        // optional human note (flagged mistakes, etc.)
  ipAddress   String?
}
```

**Scope:** all actors, all entities. This includes:
- Member self-service actions (booking created/cancelled, profile updated)
- Admin actions (certification granted, tier changed, assignment created/ended)
- System/webhook actions (Stripe payment failure → status change, Okta lifecycle event)

The audit log is never updated or deleted by application code. It is append-only.

---

## Undo

Undo is available for a **limited time window** (default: 1 hour) and covers **in-app state
only**. Actions with external side effects (Stripe, Brivo) are not automatically reversed —
they are flagged.

### Undo eligibility

| Action                          | Undoable? | Notes                                           |
|---------------------------------|-----------|-------------------------------------------------|
| Soft delete (member, resource)  | Yes       | Restore: clear `deleted_at`                     |
| Certification grant/revoke      | Yes       | Revert to prior state                           |
| Studio/storage assignment       | Yes (in-app) | Stripe add-on flagged for manual reversal    |
| Tier change                     | Yes (in-app) | Stripe subscription change flagged           |
| Booking created/cancelled       | Yes       | No external effect                              |
| Stripe payment recorded         | No        | Flag as erroneous; manual fix required          |
| Okta lifecycle event            | No        | Handled via Okta admin console                  |

### Undo UI behaviour

When an admin initiates an undo:

1. The system shows the action, timestamp, actor, and a diff of before/after state.
2. If external side effects exist, they are listed explicitly:
   > "This action created a Stripe subscription item. Undoing will restore the assignment
   > record, but the Stripe item must be removed manually. Stripe item ID: si_xxx"
3. Admin confirms. The before-state snapshot from the audit log is re-applied.
4. A new audit log entry is written: `action = "undo"`, referencing the original entry ID.

Actions outside the 1-hour window remain visible in the audit log but are not eligible for
one-click undo. Manual rollback via audit log inspection is still possible.

### Flagging mistakes

For actions that are ineligible for undo (billing events, Okta events), admins can attach a
`note` to the audit log entry flagging it as an error and recording the manual steps taken
to correct it. This keeps the audit trail coherent even when automated undo is not possible.

---

## Emergency Write Freeze

A `system_freeze` flag (stored in a single-row `SystemConfig` table) halts all write
operations platform-wide when set.

**When set:**
- All POST / PUT / DELETE API routes return `503 Service Unavailable` with message:
  `"System is in read-only mode. Contact an administrator."`
- GET routes continue to function normally
- The admin UI displays a prominent banner: "Write operations are frozen."

**Who can toggle it:** admin users with the `system:freeze` permission (a small, named group).

**Use case:** an admin suspects a data problem — a cascade that ran further than expected,
an erroneous bulk action, a webhook that fired incorrectly. They set the freeze immediately
to stop further writes, then assess the audit log and restore state without racing against
ongoing operations.

**Implementation:** middleware check on every mutating request. Single DB read per request
(cached with a short TTL to avoid hot-path overhead).

---

## Recovery Playbook (admin UI)

The admin dashboard includes an **Audit & Recovery** section:

- **Audit log viewer**: filterable by actor, entity type, entity ID, time range, action type
- **Entity history**: view the full change history of any single record
- **Undo queue**: pending undoable actions within the 1-hour window
- **Flagged actions**: audit entries marked as erroneous, with resolution notes
- **Freeze toggle**: set / clear write freeze with confirmation and reason field

---

## What This Does Not Cover

- **Database-level point-in-time recovery**: handled by DigitalOcean Managed PostgreSQL
  automated backups (daily, 7-day retention on standard plan). This is the last-resort
  recovery path, not the first.
- **Stripe billing corrections**: must be performed in the Stripe dashboard. The audit log
  flags what needs fixing; it does not automate Stripe reversals.
- **Okta user state**: managed via Okta admin console or Okta Workflows. The audit log
  records what the application requested; Okta is authoritative for its own state.

---

## Open Questions

- [ ] 1-hour undo window: is this the right default? Configurable?
- [ ] Should `system_freeze` be triggerable via a CLI command for emergency use without UI access?
- [ ] Audit log retention policy (keep forever, or archive after N years)?
- [ ] Should member self-service actions be visible to the member in their own portal history?
