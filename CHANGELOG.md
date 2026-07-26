# Changelog

All notable changes to bizkit are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow semver.
Design decisions are referenced by their `SPECIFICATION.md` D-numbers.

## [Unreleased]

### Added
- **Apply milestone (D44)** — an approved changeset now actually reaches its
  target. One generic SQLAlchemy Core DML implementation in `BaseBackend`,
  inherited by every dialect, with `dry_run()`/`apply()` sharing a code path
  that differs only in commit-vs-rollback; all-or-nothing, exactly-one-row
  assertion on update/delete (drift is reported, not absorbed), and an
  APPROVED/FAILED state re-check. `WorkflowService.apply()` returns an
  `ApplyResult(changeset, report, error)` so a FAILED transition and its
  `apply_failed` audit event survive the same commit. Exposed as
  `POST /api/v1/changesets/{id}/apply`, `bizkit apply <id> --actor <who>
  [--dry-run]`, and an Apply / Retry apply action in the changeset detail
  view (two-click confirmation naming the target table).
- **Validation rule evaluation (D11/D12/D44)** — every rule kind now has
  semantics, with a closed predicate registry (`domain/predicates.py`) so
  rule sets stay data rather than code. Validation is wired into **both**
  submit (blocking, no transition) and pre-apply, closing the long-standing
  gap where neither run existed. `POST …/validate` and `bizkit validate`
  return a structured report.
- `TableActionsOut.apply` so the UI stops inferring that affordance from
  `approve` (D25 — affordance only, fail-closed).
- **Frontend test suite** — vitest + React Testing Library + jsdom
  (`cd frontend && npm test`), covering the queue predicates, the draft
  basket's one-table scoping, and the Apply action.

### Fixed
- The draft basket no longer leaks across tables. React Router reuses
  `TableBrowser` when only the `:table` param changes, so a basket left on a
  previous table survived the switch and was filed against whichever table
  was on screen — silently misattributing rows to a table whose schema they
  did not match. The basket now carries its table, switching prompts
  keep-draft/discard (UI_SPECIFICATION.md §4.1), and sort/search/paging/edit
  state resets per table.
- Seeded demo data is now self-consistent with apply: rows a pending
  changeset inserts are absent from the target (inserting an existing key
  tripped the primary key), and the REJECTED example is a valid change
  declined on business grounds — since validation runs at submit, an invalid
  changeset can no longer reach a checker at all.

### Added (scaffold)
- Project scaffold per SPECIFICATION.md D1–D37: domain model (changeset
  state machine with rework loop and expiry — D9/D20/D21; access control
  with scoped roles — D5/D25–D28; declarative validation rule schemas —
  D11), workflow store with optimistic locking (D31), workspace config
  loading with versioning and secret indirection (D22/D23/D30), backend
  registry with lazy driver extras for the seven target technologies
  (D3/D4), WorkflowService (authorization, four-eyes, revisions, expiry,
  size caps), FastAPI `/api/v1` skeleton with health/readiness (D32/D33),
  and the `bizkit` CLI (`init-store`, `list`, `serve`, `expire`,
  `config validate|schema`).
- React SPA (Vite + React 19 + TypeScript, TanStack Query, React
  Router — D24/D28): changeset queue and detail views; built bundle
  committed to `src/bizkit/api/static/` and shipped in the wheel, so
  `bizkit serve` presents a working UI with no Node at runtime.
- Bulk CSV import (D36): `ImportService` with append and diff modes,
  all-or-nothing structured reports, type coercion from backend
  introspection, cap enforcement, audited with file hash; exposed via
  `POST /api/v1/changesets/{id}/items/import` (raw text/csv), the
  `bizkit import` CLI, and an Import CSV dialog in the table browser.
- Full workflow UI per `UI_SPECIFICATION.md` (D38–D40): sidebar shell
  with grants-driven table navigation, table browser with paged rows,
  grid-to-basket changeset drafting with diff review, reader role
  (view-only, D38), sqlite demo backend read path (D39), and
  `/api/v1/tables/.../columns|rows` endpoints with view enforcement.
