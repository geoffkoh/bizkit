# Changelog

All notable changes to bizkit are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow semver.
Design decisions are referenced by their `SPECIFICATION.md` D-numbers.

## [Unreleased]

### Added
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
