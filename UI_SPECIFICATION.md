# bizkit — UI Specification

> **Source of truth for the web UI** (spec D40), owned by the
> `ux-designer` agent and governed by the same sync protocol as
> `SPECIFICATION.md` §14: design changes land here first, then
> implementation follows. System behavior (states, roles, enforcement)
> is defined in `SPECIFICATION.md`; this document defines how it is
> presented and operated.

## 1. Personas

| Persona | Grants | Primary jobs |
|---|---|---|
| **Maker** | `submit` (+comment/view) | Browse a table, draft changes from the grid, track their changesets through review, rework after rejection/expiry |
| **Checker** | `approve`/`reject`/`apply` (+comment/view) | Work the review queue, inspect diffs against current data, decide with reasons, retry failed applies |
| **Reader** (D38) | `view` only | Look up current configuration values; see what changes are pending/decided (transparency); no commenting, no actions |
| **Admin** | grant management + view | Manage grants (store-adapter deployments only) |

Users commonly hold **unions** of these per table (D28): the UI is one
surface; capacity differences are explained contextually, never via
modes.

## 2. Design language

**Feel**: calm, professional, data-dense-but-breathable — an internal
governance tool, not a marketing site. No decoration that competes with
state semantics.

### 2.1 Tokens

- **Typography**: system stack (`system-ui, -apple-system, sans-serif`);
  base 15px/1.5; page title 1.35rem/700; section 1rem/650; table header
  0.8rem/600 uppercase +0.04em; metadata 0.8–0.85rem.
- **Spacing**: 4px scale (4/8/12/16/24/32); content max-width none in
  the work area (grids want width), 44rem for forms/prose.
- **Radius**: 6px (controls), 10px (panels/cards), 999px (badges/chips).
- **Tables are cards**: every data table carries a 1px `--border`
  outline with 10px rounded corners (`border-collapse: separate` +
  hidden overflow), **visible vertical column lines** (right border per
  cell, none on the last column), a subtly tinted header row, and row
  hover tint — the "professional grid" treatment; op tints (D39 basket)
  override hover. Utility columns are fixed-width: the grid's op-marker
  column is 2.6rem, action columns shrink to content.
- **All list tables share one component** (`DataTable`): sortable
  headers with ▲/▼ and draggable column resizing, identical to the rows
  grid — used by the Queue and the table browser's Changesets tab so
  every table behaves consistently.
- **Color**: light + dark via `prefers-color-scheme`; neutral surfaces
  (`--bg`, `--fg`, `--muted`, `--border`), one accent (`--accent`,
  blue) reserved for navigation/primary actions.
- **Semantic state colors** (fixed; never repurposed):

| Token | States/ops | Light value family |
|---|---|---|
| state-neutral | draft, withdrawn | gray |
| state-pending | submitted | blue |
| state-positive | approved, applied | green |
| state-negative | rejected, failed; op `delete` | red |
| state-warning | expired, overdue deadlines; op `update`; self-approval badge | amber |
| op-insert | op `insert` | green |

### 2.2 Fixed integrity signals (non-negotiable, from the system spec)

- State badge + revision on every changeset surface.
- `SELF-APPROVED` badge on qualifying decisions (D26/D27) — amber,
  bordered, uppercase; appears in decisions, detail, and queue rows.
- Overdue deadlines in state-warning red/amber with "(overdue)" text
  (D21).
- Audit trail always reachable from a changeset (read-only).

## 3. Application shell

```
┌────────────────────────────────────────────────────────────────┐
│ topbar:  [bizkit]                    [acting-as ▾]  [ready ●]  │
├───────────────┬────────────────────────────────────────────────┤
│ SIDEBAR       │  WORK AREA                                     │
│               │                                                │
│ WORKBENCH     │  (routed screen)                               │
│  ◦ Queue  (3) │                                                │
│               │                                                │
│ TABLES        │                                                │
│  sample       │                                                │
│   ◦ fx_rates ✎│                                                │
│   ◦ limits  ✎ │                                                │
│   ◦ audit_log👁│                                               │
│               │                                                │
│ ADMIN         │                                                │
│  ◦ Grants     │  (store-adapter deployments only)              │
└───────────────┴────────────────────────────────────────────────┘
```

- **Sidebar** (collapsible via a persistent toggle and **resizable** by
  dragging its right edge — width 170–420px, default 240px, both
  preferences in localStorage; icons-only 64px collapsed; auto-collapse
  below 900px). It is **visually distinct from the work area**: dark
  slate surface (`--side-bg #1c2536`, light text, accent-tinted active
  states) in both themes, anchoring the navigation while the work area
  stays neutral.
  - **Workbench**: Queue, with a count badge = changesets awaiting *this
    user's* review (submitted ∧ maker ≠ me ∧ approve right).
  - **Tables**: grouped by target (backend profile name), listing every
    table the caller can `view` (D38). Affordance markers: ✎ (can
    submit) vs 👁 (read-only). Active table highlighted. This satisfies
    "navigation shows the tables I can submit requests for" while also
    giving readers their view-only list.
  - **Admin**: grants management; hidden unless the store access adapter
    is active and the caller holds admin.
- **Topbar**: brand (→ Queue); identity control (dev: editable
  acting-as picker; production: display-only, from auth); readiness dot
  with config fingerprint tooltip.
- Sidebar contents come from `GET /api/v1/tables` (server-computed
  affordances — D25).

## 4. Screens

### 4.1 Table browser — `/t/:backend/:schema/:table` (primary surface, D39)

Header: table path as breadcrumb; policy chips: rules count, review/apply
TTLs, `SELF-APPROVAL LIVE` chip (amber) when effective (D27); "your
capacity" chip (maker/checker/reader union).

Tabs: **Rows** · **Changesets** · **Rules & policy**.

**Rows tab** — a data grid built on **TanStack Table** (headless — the
design system stays ours; pairs with TanStack Query; gives the column/
sort/filter/pagination model and manual mode):
- Columns from `…/columns` (introspection); values from `…/rows`.
- **Config-table scale (≤500 rows)**: one fetch, then client-side
  **search** (free-text across all columns), **sort** (click a column
  header; ▲/▼ indicator), and pagination (50/page).
- **Large tables (>500 rows)**: TanStack manual mode — pagination,
  search, and sort all run **server-side** via the rows endpoint's
  `q`/`sort`/`direction` params (in-process on the API tier;
  `total` reflects the filtered count so page math stays honest).
  Push-down into `TargetBackend.read_rows` remains the roadmap item for
  genuinely huge tables; @tanstack/react-virtual is the follow-on for
  very tall grids.
- **Columns are resizable**: drag the header's right edge (TanStack
  column sizing, 70–600px, accent-highlighted handle).
- **Pagination lives top-right of the grid**, in the toolbar row with
  search (left) and drafting actions — visible before scrolling, per
  the standard enterprise-grid pattern: ‹ **editable page-number
  input** / page-count ›, committed on Enter/blur and clamped. The
  bottom of the grid shows only the (filtered) row count.
- **Keyless tables are insert-only**: `update`/`delete` change items
  require a row key (SPECIFICATION.md §3.1), so a table without a
  primary key renders without edit/delete affordances and states why;
  browsing and Add row remain available.
- Column headers carry an amber **rule dot** when validation rules
  target that column; its tooltip lists the rule descriptions — makers
  see constraints before they draft.
- **Reader experience**: grid is plainly read-only; no edit affordances
  rendered at all.
- **Maker experience (grid-to-basket drafting, D39)**:
  - Cell/row edit (pencil on row hover → row enters edit mode) →
    `update` item; edited rows tinted state-warning with changed cells
    bold.
  - **+ Add row** (above grid) → new row form inline at top → `insert`
    item; tinted op-insert.
  - Row menu → Delete → `delete` item; row struck-through, tinted
    op-delete. Undo per row.
  - All edits accumulate in the **draft basket** — a docked bottom bar:
    "Draft: 3 changes (2 update · 1 insert) — Review & submit /
    Discard". Basket persists across pagination within the table;
    switching tables prompts (keep draft / discard).
- **Basket review step** (slide-over panel): the accumulated items as a
  before→after diff (updates show old value → new value from the loaded
  rows), title + description fields, then **Save draft** or **Save &
  submit** → `POST /api/v1/changesets` (+`submit_now`). Cap counter
  shows `items / effective max_changeset_items` (D37) and blocks past
  it with the server's message.

**Changesets tab**: the queue filtered to this table (same row anatomy
as 4.2). Visible to readers (transparency, D38).

**Rules & policy tab** (all roles, incl. readers): the table's effective
workflow policy (review/apply windows, self-approval posture, item cap)
and every validation rule as a card — kind badge (constraint blue, type
green, cross-field amber, cross-table purple), rule id, target column,
description, and parameters. Closes with the reminder that rules are
config-as-code (D11/D22): changed via a config-file PR, never in-app.

### 4.2 Queue — `/` 

Filters: **all · to review (as me) · mine**, plus a free-text search
across title/table/maker/state.
Row anatomy: title (→ detail) · table path · state badge · rev ·
items · maker · deadline (overdue treatment). Empty states point to the
Tables section (makers) or explain "nothing awaiting you" (checkers).

### 4.3 Changeset detail — `/changesets/:id`

Order: header (title, state badge, description) → metadata (table link
→ table browser, maker, revision + binding note, deadlines) → **change
items** (op-colored; when the table's rows are readable, updates render
before→after) → **Actions panel** → **Decisions** (with SELF-APPROVED
badge) → **Comments** (threaded, reply; hidden composer for readers,
D38) → **Audit trail** (table: when/actor/action/transition/detail).

**Actions panel** (state × capacity, from SPECIFICATION.md §3.3):

| State | Maker sees | Checker (not maker) sees | Reader sees |
|---|---|---|---|
| draft | Submit (primary), Withdraw | — | — |
| submitted | capacity note + Withdraw | Review note field, Approve (primary), Reject (danger; requires reason) | — |
| approved | — | (Apply — later milestone) | — |
| rejected/failed/expired | Rework (primary) | — | — |
| applied/withdrawn | — | — | — |

Reject without a reason is blocked client-side with an inline message
AND handled as the server 403. Every action button handles 403/409 with
an inline error (never silent, never a crash).

### 4.4 Grants admin — `/admin/grants` (store-adapter phase)

Grant list (principal/role/scope) + add/revoke; every change is audited;
out of scope until the D22 store adapter lands.

## 5. Role-based visibility matrix

| Surface | Maker | Checker | Reader | No grant |
|---|---|---|---|---|
| Sidebar table entry | ✎ | ✎/👁 per submit | 👁 | absent |
| Rows tab | grid + basket | grid (read-only unless also maker) | grid read-only | — |
| Changesets tab / queue rows | ✔ | ✔ | ✔ (D38) | — |
| Detail: items, decisions, audit | ✔ | ✔ | ✔ | — |
| Comment composer | ✔ | ✔ | hidden | — |
| Action buttons | per §4.3 | per §4.3 | none | — |

(Until real auth middleware lands, view filtering is advisory — the dev
deployment is open-view; the matrix is still implemented client-side so
the UX is correct on day one.)

## 6. Patterns

- **Loading**: skeleton rows for grids/lists; inline "Loading…" for
  panels. **Empty**: one sentence + the next action.
- **Errors**: inline near the triggering control; global fetch failures
  as a dismissible banner. 403 message pattern: "The server declined:
  {detail}" — affordances can be stale; enforcement is server-side.
- **Mutations**: TanStack Query invalidate-on-success (no optimistic
  state transitions — workflow truth comes from the server).
- **Destructive confirmations**: Withdraw and Discard-basket confirm
  inline (two-click); Reject is gated by its required reason instead.
- **Keyboard/a11y**: visible focus rings; grids navigable by arrow keys
  (later phase); badges carry `aria-label` (e.g. "state: submitted");
  AA contrast in both themes.
- **Responsive**: designed for ≥1100px; below that the sidebar
  collapses to icons; mobile is out of scope (governance work is a
  desktop job).

## 7. Phasing

1. **P1 — Shell & browse** (with D38/D39 backend work): sidebar shell,
   tables from grants incl. reader view, table browser Rows (read-only)
   + Changesets tabs, queue/detail restyled into the shell.
2. **P2 — Grid drafting**: edit/insert/delete → draft basket → review
   slide-over → create/submit; before→after diffs in detail.
3. **P3 — Later**: validation report surfaces (D12), CSV import into
   basket (D36), apply/retry actions, grants admin (D22),
   keyboard grid navigation. (Rules & policy tab, grid search/sort, and
   the collapsible colored sidebar shipped with P2.)

## 8. Open questions (for future decisions)

- Row-level drill-in (record page) vs grid-only editing.
- Saved views/filters per table.
- Pending-change indicators on grid rows that appear in open changesets
  ("this row has 2 pending changes").
