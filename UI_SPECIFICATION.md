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
| **Reader** (D38) | `view` only | Look up current configuration values; see what changes are pending/decided **and the full audit trail** (transparency); no commenting, no actions. This is also the **auditor** persona — there is deliberately no separate auditor role (D43) |
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
  0.8rem/600 uppercase +0.04em; metadata 0.8–0.85rem. **Numeric/ID
  columns use `font-variant-numeric: tabular-nums`** so values align
  vertically in the grid — the single highest-leverage typographic
  detail for a data-dense UI reading as "crafted" rather than "browser
  default".
- **Spacing**: 4px scale — `space-1`=4 `space-2`=8 `space-3`=12
  `space-4`=16 `space-6`=24 `space-8`=32 `space-10`=40 (px); content
  max-width none in the work area (grids want width), 44rem for
  forms/prose. Component padding is always a scale value, never a
  one-off pixel figure.
- **Radius**: 6px (controls), 10px (panels/cards), 999px (badges/chips).
- **Tables are cards**: every data table carries a 1px `--border`
  outline with 10px rounded corners (`border-collapse: separate` +
  hidden overflow), **visible vertical column lines** (right border per
  cell, none on the last column), a subtly tinted header row, and row
  hover tint — the "professional grid" treatment; op tints (D39 basket)
  override hover. Utility columns are fixed-width: the grid's op-marker
  column is 2.6rem, action columns shrink to content. Grids themselves
  stay **flat** (border only, `shadow-none`) — elevation is reserved for
  things that float above the page (§2.2), so the resting UI never looks
  busier than the data it holds.
- **All list tables share one component** (`DataTable`): sortable
  headers with ▲/▼ and draggable column resizing, identical to the rows
  grid — used by the Queue and the table browser's Changesets tab so
  every table behaves consistently.
- **Iconography**: one consistent outline icon set (Feather/Lucide-style —
  24×24 grid rendered at 16–18px, 1.75px stroke, round caps/joins,
  `currentColor` so icons inherit text/muted/state color automatically
  wherever they're used). **Emoji are never UI chrome** — no ✎/👁/☰/⋮/✕
  as literal glyphs; those become icons (`pencil`, `eye`, `sidebar`,
  `more-vertical`, `close`) from the same set as tree disclosure
  chevrons, sort arrows, and search. One shared sprite/icon component,
  not ad hoc per-screen choices — an inconsistent icon weight or style
  reads as unpolished as an inconsistent shadow would.
- **Color**: light + dark via `prefers-color-scheme`; neutral surfaces
  (`--bg`, `--fg`, `--muted`, `--border`), one accent (`--accent`,
  blue) reserved for navigation/primary actions. Five additions for
  layering and accessibility, same rules (light/dark pair, never
  repurposed): `--bg-hover` (row/list-item hover tint — a step between
  `--bg` and `--border`, distinct from the semantic op/state tints);
  `--bg-subtle` (the tinted table header row and other at-rest
  secondary surfaces — one step off `--bg`, weaker than `--bg-hover` so
  a hovered row still reads as hovered against a tinted header);
  `--border-strong` (the "slight `--border` darkening" on button/card
  hover in §2.4, and the dark-theme `shadow-sm` ring); `--accent-fg`
  (text/icons *on* an accent fill — must clear AA against `--accent` in
  both themes; accent hover/pressed derive as
  `color-mix(in srgb, var(--accent) 88%, var(--fg))` rather than getting
  their own tokens); and `--focus-ring` (the accent at reduced opacity,
  e.g. `color-mix(in srgb, var(--accent) 45%, transparent)`) for the
  focus treatment in §2.4.
- **Semantic families are triples, not single hues**: every state/op
  token below resolves to a base, a `-fg` (text on neutral ground), a
  `-border`, and a `-bg` tint, so badges, chips, and row tints all draw
  from one pair instead of each screen mixing its own alpha. Grid row
  tints for the D39 basket are their own weaker step
  (`--row-tint-update|insert|delete`) — a tinted *row* must stay
  readable under text, where a badge fill does not.
- **Semantic state colors** (fixed; never repurposed):

| Token | States/ops | Light value family |
|---|---|---|
| state-neutral | draft, withdrawn | gray |
| state-pending | submitted | blue |
| state-positive | approved, applied | green |
| state-negative | rejected, failed; op `delete` | red |
| state-warning | expired, overdue deadlines; op `update`; self-approval badge | amber |
| op-insert | op `insert` | green |

One deliberate exception, scoped and named so it can't spread: the
**rule-kind** badges in the Rules & policy tab (§4.1) need a fourth hue
for `cross_table`, which no state family owns. That is
`--kind-cross-table` (purple) — valid *only* on a rule-kind badge, never
on a state, op, or row tint. The other three kinds reuse
state-pending (constraint), op-insert (type), and state-warning
(cross-field).

### 2.2 Elevation

Airtable/Linear-grade UIs read as "crafted" largely because shadow is
used sparingly and consistently to mean exactly one thing: *this surface
is floating above the page*. Four steps, applied by role — never picked
ad hoc per component:

| Token | Used for | Light | Dark |
|---|---|---|---|
| `shadow-none` | Grids, cards, sidebar, at-rest surfaces | none (border only) | none (border only) |
| `shadow-sm` | Hovered row-action buttons, dragged column resizer | `0 1px 2px rgba(0,0,0,.06)` | none — use a 1px lighter `--border` highlight instead |
| `shadow-md` | Dropdowns, popovers, tooltips, the column rule-dot tooltip | `0 4px 12px rgba(0,0,0,.12)` | `0 4px 12px rgba(0,0,0,.4)` + 1px `--border` |
| `shadow-lg` | Basket review slide-over, modals/confirmations, the docked draft-basket bar | `0 8px 30px rgba(0,0,0,.16)` | `0 8px 30px rgba(0,0,0,.5)` + 1px `--border` |

Dark theme leans on the 1px border more than the shadow (shadows read
as muddy haze on dark surfaces, not depth) — this is a deliberate
light/dark asymmetry, not an oversight. In dark, `shadow-sm` is an
**outset spread-only ring** (`0 0 0 1px var(--border-strong)`), not an
inset one, so a component can write `box-shadow: var(--shadow-sm)`
unconditionally and get the right treatment per theme.

The docked basket bar (§4.1) is grouped with `shadow-lg` rather than
getting a step of its own: it is docked, but it floats above the grid
and is the same "you are about to commit something" surface class as the
review slide-over it opens.

### 2.3 Motion

Motion exists to communicate cause → effect, never for decoration.
Three durations, two easings — same rule as elevation, picked by role:

| Token | Value | Used for |
|---|---|---|
| `duration-fast` | 100ms | Hover/press tints, row-action fade-in, checkbox/toggle |
| `duration-base` | 160ms | Dropdown/popover open-close, tab switch, tooltip |
| `duration-slow` | 240ms | Slide-over panel enter/exit, modal enter/exit |
| `easing-enter` | `cubic-bezier(0.2, 0, 0, 1)` | Anything appearing (ease-out — fast start, gentle stop) |
| `easing-exit` | `cubic-bezier(0.4, 0, 1, 1)` | Anything disappearing (ease-in) |

- Loading skeletons shimmer on a slow, low-contrast loop
  (`--duration-shimmer`, 1800ms) — never the attention-grabbing kind.
  Two further durations are tokens rather than inline figures for the
  same reason: `--duration-spin` (800ms, the `spinner` icon's rotation)
  and `--duration-toast` (4000ms, the §6 auto-dismiss TTL).
- Mutations stay non-optimistic (§6) but the *affordance* still responds
  instantly (button press state, disabled state) so the UI never feels
  inert while a request is in flight.
- `prefers-reduced-motion: reduce` disables all non-essential
  transitions (panel slides, shimmer) — state changes still happen,
  just as instant cuts.

### 2.4 Interaction states

Every interactive element defines all four states below using the
tokens above — an element with only a "rest" and a "click handler" is
an unfinished component, not a smaller one:

- **Rest**: the default, per component spec.
- **Hover**: `--bg-hover` tint (rows/menu items) or `shadow-sm` +
  slight `--border` darkening (buttons/cards), transitioning over
  `duration-fast`. Row-hover-reveal icons (edit pencil, row menu — D39)
  fade in over `duration-fast`, not a hard toggle.
- **Focus-visible**: a 2px `--focus-ring` outline with 2px offset on
  every focusable element, keyboard or pointer-triggered per the
  `:focus-visible` semantics — never suppressed with
  `outline: none` without a replacement.
- **Disabled**: 50% opacity, `cursor: not-allowed`, no hover/press
  response (hover rules are guarded, not merely overridden); disabled
  controls still explain *why* where the reason isn't obvious (e.g. "cap
  reached", "keyless table — updates need a row key"). That explanation
  uses the **shared `Tooltip` primitive**, not a native `title`: the
  same bubble (`shadow-md`, `duration-base`) that the truncate-and-hover
  cell renderer in §4.1 and the sidebar's long-name treatment (§3) sit
  on top of. One tooltip component, three consumers — a native `title`
  is not an acceptable substitute, because it can't be styled, is
  slow to appear, and gets shadowed wherever a real tooltip is nearby.

### 2.5 Fixed integrity signals (non-negotiable, from the system spec)

- State badge + revision on every changeset surface.
- `SELF-APPROVED` badge on qualifying decisions (D26/D27) — amber,
  bordered, uppercase; appears in decisions, detail, and queue rows.
  ⚠️ **Queue rows are blocked on an API change**: `ChangesetOut` carries
  no `self_approved` field, and the only client-side alternative is an
  N+1 `/decisions` fetch per row — which is not an acceptable way to
  render a list. The badge is live in the decisions list and on the
  changeset detail header; it will be absent from queue rows until
  `ChangesetOut` gains the boolean (a UX-driven API need for
  SPECIFICATION.md §7).
- Overdue deadlines in state-warning (amber) with "(overdue)" text
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
│  Queue    (3) │                                                │
│               │                                                │
│ TABLES        │                                                │
│  ▾ postgres-prod                                                │
│    ▾ sample   │                                                │
│      fx_rates    [pencil]                                      │
│      limits      [pencil]                                      │
│      audit_log   [eye]                                         │
│    ▸ risk     │                                                │
│  ▸ snowflake-eu                                                 │
│               │                                                │
│ ADMIN         │                                                │
│  Grants       │  (store-adapter deployments only)              │
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
  - **Tables: a collapsible tree**, mirroring the `(backend, schema,
    table)` scope model (SPECIFICATION.md §3.2) exactly rather than
    inventing a separate navigation shape: **backend → schema → table**,
    listing every table the caller can `view` (D38). **Progressive
    disclosure**: the schema level only renders when a backend exposes
    more than one schema to this caller — a single-schema backend goes
    straight from backend to its tables, so the common case (one
    schema) never carries a redundant middle node. Backend and schema
    nodes are native disclosure widgets (expand/collapse, keyboard
    operable) with a `chevron` icon and a muted `server`/`folder` icon;
    expand/collapse state persists per node in localStorage alongside
    the width/collapse prefs above. Table leaves carry the affordance
    icon — `pencil` (can submit) or `eye` (read-only) — **never the
    literal ✎/👁 emoji** (§2.1 Iconography). Active table highlighted.
    **Names too long for the sidebar's current width** (user-resized
    narrower, or just a long name) use the same truncate + `shadow-md`
    hover-tooltip component as long grid cells (§4.1) — one shared
    component, not a second implementation of the same problem.
    This satisfies "navigation shows the tables I can submit requests
    for" while also giving readers their view-only list, and scales to
    targets that expose many schemas (or many databases-as-schemas)
    without flattening them into one long alphabetical list.
    A backend that exposes >1 schema where one of them is null labels
    that node **`(default)`**; the route still uses the `-` placeholder
    segment.
    **Accessibility pattern**: the tree implements APG *Disclosure
    Navigation* (nested lists, `<button aria-expanded>` per branch,
    arrow-key convenience) rather than formal `role="tree"` with a
    roving tabindex — every row stays in the tab order, which is right
    at nav-rail scale. Revisit if a single caller can routinely see
    hundreds of tables.
    **In the 64px rail** the tree flattens to an icon list: chevrons
    hidden, indentation zeroed, backend `server` icons and table
    affordance icons kept in DOM order. Because the label is the only
    thing identifying a row, **every rail icon carries the shared
    tooltip** with its full name (plus the backend/schema breadcrumb for
    tables) — a rail you cannot read is worse than no rail.
    Below 900px the auto-collapse **wins over the user's toggle**: the
    toggle renders disabled with the §2.4 reason tooltip. The stored
    width and collapse preferences are never overwritten by the
    breakpoint, so a user's chosen width returns when the viewport grows
    back.
  - **Admin**: grants management; hidden unless the store access adapter
    is active and the caller holds admin.
- **Topbar**: brand (→ Queue); a **command palette trigger** (search
  icon + "Search…" + a `⌘K`/`Ctrl+K` hint, styled as a subdued input-like
  pill, never a loud button); identity control (dev: editable
  acting-as picker; production: display-only, from auth); readiness dot
  with config fingerprint tooltip.
  - The identity control is gated on `GET /api/v1/me`'s
    `auth.provider` (D42): the editable dev picker renders **only** for
    `none`, everything else gets the read-only display. An **absent**
    `auth` object is read as `none`, which is today's posture — the
    backend `auth/` module does not exist yet and `MeOut` returns only
    `{user}`. This is deliberate so the gate becomes correct the moment
    the backend starts reporting a provider, with no frontend change.
    The `oidc` sign-in redirect and `ldap` login form (plus their
    session-expired and sign-in-failed states) remain undesigned and
    unimplemented.
- **Command palette** (`⌘K`/`Ctrl+K`, or the topbar trigger): a centered
  overlay (`shadow-lg`, fade+scale via `duration-base`/`easing-enter`,
  same scrim treatment as the basket slide-over) with a search input and
  live-filtered, grouped results — **Tables** (icon = the same
  pencil/eye affordance markers as the sidebar tree, with the
  backend/schema breadcrumb as secondary text), **Changesets** (state
  badge + title), **Actions**. Arrow keys move a
  selection, Enter activates it, Esc or a scrim click closes it — it is
  a second index onto the same navigable set as the sidebar tree and
  queue, not a separate feature with its own data: it reads the same
  tables/changesets query caches the sidebar and queue already populate
  and issues **zero additional requests**. Empty/no-match state
  follows the one-sentence convention (§6).
  - **Ranking and caps**: prefix matches rank above substring matches,
    then alphabetical; fixed group order (Tables → Changesets →
    Actions); 8 results per group, and a truncated group shows a muted
    "+N more — keep typing" line so the cap is never silent. An **empty
    query lists everything** (still capped), so the palette doubles as a
    browse affordance rather than an empty box. Fuzzy matching and a
    recency group are deliberately deferred until a deployment's table
    count demands them.
  - **Actions group**: "Go to Queue", "New changeset", and
    "Collapse/Expand navigation" (label reflects current state; omitted
    entirely while railed by the 900px breakpoint, where the toggle is
    disabled).
  - **Keyboard**: `⌘K`/`Ctrl+K` toggles — but is **ignored while the
    user is typing** in an input/textarea/select/contenteditable, and
    while a modal or slide-over is open (the palette never stacks over
    another floating surface). Up/Down move with wrapping, Home/End jump
    to first/last, Enter activates, Esc closes. Focus is trapped in the
    search input and driven by `aria-activedescendant`
    (`role="combobox"` + `role="listbox"`/`option`), so Tab is swallowed
    rather than escaping the overlay; focus returns to the topbar
    trigger on every close path.
- Sidebar contents come from `GET /api/v1/tables` (server-computed
  affordances — D25); the response's `schema` field drives the tree
  grouping, so a caller who can see a table in a normally-hidden schema
  still gets a (single-item) schema node rather than a silent gap.

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
  header), and pagination (50/page).
- **Large tables (>500 rows)**: TanStack manual mode — pagination,
  search, and sort all run **server-side** via the rows endpoint's
  `q`/`sort`/`direction` params (in-process on the API tier;
  `total` reflects the filtered count so page math stays honest).
  Push-down into `TargetBackend.read_rows` remains the roadmap item for
  genuinely huge tables; @tanstack/react-virtual is the follow-on for
  very tall grids.
- **Sort is one affordance regardless of where it runs**: every sortable
  header shows the same three-state icon (neutral `sort` → accent
  `arrow-up` → accent `arrow-down` → back to neutral), client- or
  server-backed. The *only* visible difference on a server-sorted table
  is that clicking swaps the icon for a small `spinner` while the
  request is in flight, and the other headers dim/ignore clicks until
  it resolves (prevents a second sort request racing the first) — a
  maker should never need to know or care which mode a given table is
  in. **Implementation note**: the spinner is currently keyed to "a rows
  refetch is in flight" rather than "a sort request is in flight" (the
  paged query's `isFetching` covers sort, search, and page changes
  alike), so a page change also briefly makes headers inert. Harmless —
  it still prevents racing — but it is a deviation from the letter of
  this clause.
- **Columns are resizable**: drag the header's right edge (TanStack
  column sizing, 70–600px, accent-highlighted handle, `cursor:
  col-resize`). Manual widening is the maker's own remedy for a column
  they want to read in full without hovering (below).
- **Long cell/header content never grows the row or breaks the grid**:
  text truncates with an ellipsis at the column's current width
  (resized width wins over any default). A truncated cell shows its
  full value in a `shadow-md` hover tooltip (§2.2) — cheap, read-only
  inspection without entering edit mode. Editing a long-text column
  (row edit, D39) renders a multi-line `textarea` instead of a
  single-line input, so the full value is visible and editable at once.
  ⚠️ "Flagged long-text" has **no data to key off today**: `ColumnOut` is
  `{name, type, nullable, primary_key}` and `type` is the normalised
  domain type (`string`/`integer`/…) with no length. The implementation
  falls back to the *value's* length (≥80 chars ⇒ `textarea`), which
  covers the real cases but cannot know that an empty `varchar(4000)` is
  a long-text column. A `max_length` or `long_text` field on `ColumnOut`
  would close it properly (UX-driven API need for SPECIFICATION.md §7).
  This is a deliberate three-tier answer (truncate → hover for the full
  value → widen the column or edit for real), not a single trick that
  only half-solves it; it's also the intended interim answer to the
  row-level drill-in question in §8 — a record-detail page can replace
  the tooltip tier later without changing the other two.
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

- **Loading**: skeleton rows for grids/lists (shimmer per §2.3); inline
  "Loading…" for panels. **Empty**: one sentence + the next action.
- **Errors**: inline near the triggering control; global fetch failures
  as a dismissible banner. 403 message pattern: "The server declined:
  {detail}" — affordances can be stale; enforcement is server-side.
- **Mutations**: TanStack Query invalidate-on-success (no optimistic
  state transitions — workflow truth comes from the server); button
  press/disabled states (§2.4) still respond instantly so the UI
  doesn't feel inert while a request is in flight.
- **Toasts**: every successful or failed workflow mutation (submit,
  approve, reject, save draft, discard) confirms via a transient toast
  — top-right stack, `shadow-md`, slide+fade in on `duration-base`,
  auto-dismiss after ~4s with a shrinking progress bar, always
  individually dismissible. Toasts are a *supplement* to inline
  errors/banners (§ above), never a replacement for them — a 403 still
  gets its inline message next to the control that triggered it; the
  toast is just the ambient "it worked / it didn't" signal for actions
  whose result isn't otherwise visible on screen.
- **Destructive confirmations**: Withdraw and Discard-basket confirm
  inline (two-click); Reject is gated by its required reason instead.
- **Floating surfaces** (dropdowns, popovers, tooltips, the basket
  review slide-over, modals) use the elevation and motion tokens in
  §2.2/§2.3 — never a one-off shadow or transition duration.
- **Keyboard/a11y**: every focusable element shows the `--focus-ring`
  treatment (§2.4), never suppressed without a replacement; grids
  navigable by arrow keys (later phase); badges carry `aria-label`
  (e.g. "state: submitted"); AA contrast in both themes.
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

P1 and P2 are implemented, including the §2.1–2.5 craft layer, the
sidebar tree, the command palette, and the toast system. Known gaps
carried into P3, each recorded at its clause above: `SELF-APPROVED` on
queue rows and the long-text column flag (both blocked on an API field),
keyboard column resizing (the sidebar separator has the full treatment;
TanStack column sizing is still drag-only), and the server-sort
spinner's refetch keying.

## 8. Open questions (for future decisions)

- Row-level drill-in (record page) vs grid-only editing.
- Saved views/filters per table.
- Pending-change indicators on grid rows that appear in open changesets
  ("this row has 2 pending changes").
