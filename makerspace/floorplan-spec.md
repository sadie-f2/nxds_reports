# Floor Plan & Space Management — Spec v1.0

## Scope

This spec covers how the application represents, imports, displays, and links to physical spaces
(studios, shops, rooms) defined in the facility's AutoCAD drawings. It is a v1.0 feature.

---

## Definitions

**Space** — any physically bounded area tracked in the system: studio unit, shop, meeting room,
common area. Every Space node in the Resource tree has an optional floor plan reference.

**Studio** — a private space leased by a member or group of members. Defined as N × 50 SF base
units; sizes offered are 50, 100, and 200 SF. ~250 units exist across two buildings.

**Base unit** — the smallest independently assignable studio area (50 SF). Larger studios are
always contiguous groups of base units assigned together. Whether a group can be subdivided is
a staff-managed configuration flag, not auto-derived from the DXF.

---

## Floor Plan Source Format

The facility has AutoCAD DXF files for all spaces. The DXF is a simplified schematic:

- Standard AutoCAD blocks define space types (studio unit, shop, room, wall, door, etc.)
- Each space block carries a stable attribute: `SPACE_ID` (e.g. `STUDIO_201`, `SHOP_LASER`)
- `SPACE_ID` is the permanent link between the DXF and the application database
- IDs are set once and never changed; they are the primary join key

### AutoCAD Block Vocabulary

Staff define and maintain a block vocabulary in AutoCAD. Minimum required blocks:

| Block name     | Meaning                        | Required attribute |
|----------------|--------------------------------|--------------------|
| `STUDIO_UNIT`  | 50 SF studio base unit         | `SPACE_ID`         |
| `SHOP`         | Equipment shop                 | `SPACE_ID`         |
| `MEETING_ROOM` | Bookable meeting room          | `SPACE_ID`         |
| `COMMON_AREA`  | Non-bookable common space      | `SPACE_ID`         |
| `DOOR`         | Door (no ID required)          | —                  |
| `WALL`         | Wall segment (no ID required)  | —                  |

Additional block types may be added by staff; unknown blocks are rendered as outlines with a
label and do not cause import errors.

---

## DXF → SVG Import Pipeline

A standalone Python script (`tools/dxf_to_svg.py`) converts DXF files to SVG for use in the UI.

### Script responsibilities

1. Parse the DXF using `ezdxf`
2. Extract all INSERT entities (block references) and LWPOLYLINE/LINE geometry
3. For each block reference with a `SPACE_ID` attribute:
   - Emit an SVG `<g>` element with `data-space-id="STUDIO_201"` and `data-block-type="STUDIO_UNIT"`
   - Render the block's geometry as child SVG shapes
4. Render non-block geometry (walls, annotations) as plain SVG paths
5. Output a self-contained SVG file: `public/floorplans/<building>_<floor>.svg`

### Stable ID contract

- `data-space-id` values are the join key to the database `spaces.external_id` column
- The SVG renderer queries the database for live state (occupancy, bookings) using these IDs
- IDs must never change once assigned in the DXF

### Import modes

**Full import** — initial setup or full rebuild:
```
python tools/dxf_to_svg.py --input building_a_floor1.dxf --output public/floorplans/a_1.svg
```

**Diff mode** — for updates after a DXF revision:
```
python tools/dxf_to_svg.py --input building_a_floor1.dxf --diff --output public/floorplans/a_1.svg
```

Diff mode reports:
- New `SPACE_ID` values not in the current SVG (additions)
- `SPACE_ID` values in the current SVG missing from the new DXF (removals — flagged as warnings)
- Geometry changes to existing IDs (updates)
- IDs present in both with no change (no-ops)

Removals of existing `SPACE_ID` values require explicit confirmation; they are not applied
silently. A `SPACE_ID` that exists in the database as an active assignment blocks removal until
the assignment is ended.

---

## Database Schema

```prisma
model FloorPlan {
  id         String   @id @default(cuid())
  building   String                          // e.g. "A", "B"
  floor      Int
  svgPath    String                          // path under /public/floorplans/
  updatedAt  DateTime @updatedAt
  spaces     Space[]
}

model Space {
  id          String    @id @default(cuid())
  externalId  String    @unique               // matches data-space-id in SVG
  name        String
  blockType   String                          // STUDIO_UNIT, SHOP, MEETING_ROOM, etc.
  floorPlanId String
  floorPlan   FloorPlan @relation(fields: [floorPlanId], references: [id])
  resourceId  String?   @unique               // link to Resource tree node
  resource    Resource? @relation(fields: [resourceId], references: [id])
  createdAt   DateTime  @default(now())
  updatedAt   DateTime  @updatedAt
}
```

`Space` is the bridge between the physical floor plan and the Resource tree. Every bookable or
leasable area has both a `Space` record (floor plan geometry) and a `Resource` record (booking
and access logic). Non-bookable common areas have a `Space` record but no `Resource`.

---

## Browser Display

Floor plans are displayed as inline SVG embedded in the page (not `<img>` or `<object>`).
Inline SVG allows the application to:

- Query and update DOM elements by `data-space-id`
- Apply CSS classes for occupancy state (vacant, occupied, selected)
- Attach click/hover handlers for booking or assignment flows

### Rendering approach

1. The SVG file is served from `/public/floorplans/` and fetched at page load
2. The client queries the API for current space states (occupancy, active bookings, member name)
3. The SVG DOM is updated: fill colours and tooltip content applied per `data-space-id`
4. Clicking a space opens a panel: space details, current occupant (if any), actions available
   to the current user (book, assign, view history)

### Colour states (studios)

| State        | Fill           |
|--------------|----------------|
| Vacant       | `#d4edda` (green) |
| Occupied     | `#f8d7da` (red)   |
| My studio    | `#cce5ff` (blue)  |
| Selected     | `#fff3cd` (amber) |

Shops and meeting rooms use analogous booking-state colours.

---

## Admin Workflows

- **Import floor plan**: run `dxf_to_svg.py`, commit SVG to repo, trigger sync in admin UI
- **Sync spaces**: admin action reads the SVG, creates/updates `Space` records for all
  `data-space-id` elements, reports additions and any flagged removals
- **View floor plan**: full interactive floor plan with live occupancy overlay
- **Assign studio from floor plan**: click vacant unit → assign to member → Stripe add-on created

## Member Portal

- **View floor plan**: read-only occupancy view; click own studio to see assignment details
- Studio units not occupied by the member are shown as occupied/vacant but without tenant name

---

## Operational vs Structural Changes

| Change type                         | Source of truth | How applied                     |
|-------------------------------------|------------------|---------------------------------|
| Member assigned to studio           | Application DB   | Click-to-assign in admin UI     |
| Studio subdivided or merged         | DXF + staff flag | DXF re-export → diff import     |
| New room added to building          | DXF              | DXF re-export → diff import     |
| Room renamed                        | Application DB   | Edit in admin UI (not DXF)      |
| Wall moved (layout change)          | DXF              | DXF re-export → full import     |

The DXF is the source of truth for geometry only. All operational state (assignments, bookings,
names, descriptions) lives in the database and is never overwritten by a DXF import.

---

## Out of Scope (v1.0)

- Real-time occupancy from badge readers or sensors
- 3D models or rendered floor plans
- Multiple floors displayed simultaneously
- Wayfinding or navigation overlays
- Print-to-PDF floor plan export

---

## Open Questions

- [ ] Confirm DXF file organisation: one file per floor per building, or combined?
- [ ] Who maintains `SPACE_ID` assignment in AutoCAD? (staff responsibility)
- [ ] Studio sub-unit policy: which units are non-subdivisible? Staff to provide initial list.
- [ ] Which floor plan(s) to use as the pilot for import testing?
