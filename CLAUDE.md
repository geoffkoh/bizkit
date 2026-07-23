# CLAUDE.md: bizkit

> **Scope:** This file governs the bizkit project and supersedes any
> workspace-level guidance describing other projects for all work under
> `bizkit/`. It is self-contained: every rule that applies here is stated
> here.

## Project Overview
bizkit ("Business Configuration Toolkit") is a data-configuration utility
library. Business configuration lives in database tables across seven
technologies — Oracle, MSSQL, MySQL, PostgreSQL, Percona, Snowflake,
Databricks — and bizkit manages changes to those tables through a
maker-checker workflow with threaded commenting, validation of entries, and a
full audit trail. Interfaces: Python library, `bizkit` CLI (click), REST API
(FastAPI), and a React web UI (built bundle ships in the wheel).

## Specification Is the Source of Truth
`SPECIFICATION.md` records every design decision (ADR-style decision log,
domain model, enforcement points, module layout); `UI_SPECIFICATION.md`
does the same for the web UI (information architecture, design tokens,
screens, role-based visibility — spec D40). Read them before designing
or implementing anything non-trivial. **Whenever the specification changes,
update this file, every affected agent in `.claude/agents/`, and every
affected skill in `.claude/skills/` in the same change** so they reflect the
current spec. If code and spec disagree, fix one explicitly — never leave
them divergent.

## Domain Glossary
- **Target DB**: a customer database holding configuration tables. bizkit
  never writes to it except when applying an approved changeset.
- **Changeset**: the aggregate for a proposed change — a set of change items
  against one target table, moving through the state machine below.
- **Change item**: one insert/update/delete of a single row.
- **Maker**: the user who drafts and submits a changeset.
- **Checker**: the user who approves or rejects it. A maker can never check
  their own changeset.
- **Role / Action / Scope / Grant**: explicit access control. Roles
  (`maker`, `checker`, `reader` — view-only, spec D38; also the auditor
  persona, no separate `auditor` role per D43 — and `admin`)
  grant actions (`submit`, `approve`,
  `reject`, `apply`, `comment`, `view`) on scopes — `(backend, schema,
  table)` patterns with `*` wildcards — via grants. `view` deliberately
  covers both table data and the table's changesets/decisions/audit
  trail (one action, not split — D43). Authorization goes
  through the `AccessPolicy` port; adapters are file-backed grants from
  the workspace config file (default, spec D22), a store-backed grants
  table (optional, for runtime administration), or external IAM
  (group-mapping). Authentication is always external — bizkit never
  stores credentials.
- **Workflow store**: bizkit's own database (SQLite in dev, Postgres in
  prod) holding changesets, approvals, comments, and audit events. It may
  share an instance with a target, but always in its own database/schema
  with separate least-privilege credentials, on an OLTP-suitable engine —
  separation is logical, not necessarily physical (spec D29).
- **Audit event**: an immutable record written for every state transition, in
  the same transaction as the transition.
- **Rule / validation report**: declarative validation rules (type,
  constraint, cross-field, cross-table) producing structured
  `ValidationIssue`s collected into a `ValidationReport`. Rule sets are
  versioned per registered configuration table — by content fingerprint
  under the default file-first workspace config (spec D22), or as rows in
  the optional store-backed registry (`bizkit_table_configs` /
  `bizkit_rule_sets`).
- **Identity / `AuthProvider`** (spec D42): authentication ("who is
  this?") is a separate port from `AccessPolicy` ("what can they do?").
  Every `AuthProvider` adapter (`none`, `oidc`, `ldap`, `token` —
  `saml` deferred) produces the same `Identity` (principal, display
  name, email, groups), which feeds the existing `GroupMappingAccessPolicy`
  unchanged. Config-selected via `auth.provider`, same pattern as
  `access.provider` and backend selection.

State machine (rework loop per spec D20 — items editable only in DRAFT;
each submit increments the changeset `revision`; approvals bind to the
exact revision reviewed):

```
DRAFT → SUBMITTED → (APPROVED | REJECTED)
APPROVED → APPLIED | FAILED
REJECTED, FAILED → DRAFT      (rework by the maker; next submit = new revision)
FAILED → APPLIED              (retry of the same approved revision)
SUBMITTED, APPROVED → EXPIRED (review/apply deadline lapses; actor system:expiry)
EXPIRED → DRAFT               (rework by the maker)
DRAFT, SUBMITTED → WITHDRAWN
APPLIED, WITHDRAWN are terminal
```

Expiry (spec D21): submit snapshots `review_deadline`, approve snapshots
`apply_deadline` (per-table TTLs in the table registry, falling back to
config defaults; unset = no expiry). Every workflow operation checks
deadlines first (guard-on-action); `bizkit expire` sweeps proactively.
DRAFTs never expire.

## Tech Stack & Architecture
- **Language:** Python 3.13+, uv-managed, src layout, `py.typed`.
- **Pattern:** Domain driven design, Test driven development.
- **Layering** (dependencies point left only):
  `domain` ← `store` / `workspace` / `backends` / `access` / `auth` ←
  `services` ← `api` / `cli`
  - `domain/`: pure model (stdlib + pydantic only, no I/O). Ports (Protocols)
    live in `domain/ports.py`.
  - `store/`: SQLAlchemy persistence of workflow state, implements the
    repository ports; optional store-backed config adapters
    (`StoreAccessPolicy`, `StoreTableRegistry`).
  - `workspace/`: file-first config adapters (spec D22) — loads the
    YAML/JSON workspace file into `FileTableRegistry` and
    `FileAccessPolicy` (the defaults). The file declares a required
    `version` (current: 1) and is validated against the pydantic-generated
    JSON Schema; unknown keys are hard errors (spec D23).
  - `backends/`: one adapter per target technology, implements
    `TargetBackend`.
  - `access/`: external IAM adapters for the `AccessPolicy` port
    (group-mapping first; remote decision engines later).
  - `auth/`: pluggable `AuthProvider` adapters (spec D42) — `none`
    (trusted dev header, gated behind `allow_insecure_dev_mode`), `oidc`
    (generic OIDC/OAuth2 — PingOne, Okta, Azure AD, etc., one adapter
    via config only), `ldap` (directory bind, credentials discarded
    after verification), `token` (static bearer token, machine-only);
    `saml` deferred. Produces `Identity`, consumed by `access/groups.py`'s
    `GroupMappingAccessPolicy` — authentication and authorization stay
    separate ports.
  - `services/`: application layer. `WorkflowService` is the only place state
    transitions happen.
  - `api/` and `cli/`: thin delivery layers over services.
- **Workflow store is sync SQLAlchemy** — the Snowflake/Databricks dialects
  are sync-only, so the whole persistence tier stays sync and FastAPI bridges
  via `fastapi.concurrency.run_in_threadpool`. Do not convert the store or
  backends to the async engine.

### Target backends
| Backend | Extra | Driver | SQLAlchemy URL prefix |
|---|---|---|---|
| Oracle | `bizkit[oracle]` | oracledb | `oracle+oracledb://` |
| MSSQL | `bizkit[mssql]` | pyodbc | `mssql+pyodbc://` |
| MySQL | `bizkit[mysql]` | pymysql | `mysql+pymysql://` |
| Percona | `bizkit[mysql]` | pymysql | `mysql+pymysql://` (rides the MySQL dialect) |
| PostgreSQL | `bizkit[postgres]` | psycopg | `postgresql+psycopg://` |
| Snowflake | `bizkit[snowflake]` | snowflake-sqlalchemy | `snowflake://` |
| Databricks | `bizkit[databricks]` | databricks-sqlalchemy | `databricks://` |

Drivers are optional and lazy-imported; a missing driver raises
`BackendNotInstalledError` naming the exact `pip install 'bizkit[<extra>]'`.

## Environment & Commands
- **Manager:** uv
- **Install deps:** `uv sync`
- **Run CLI:** `uv run bizkit --help`
- **Run API server:** `uv run bizkit serve` (FastAPI on :8091, serves the
  built SPA from `src/bizkit/api/static/` when present)
- **Run tests (fast suite):** `uv run pytest` (integration tests auto-skip)
- **Run integration matrix:** see the `db-matrix-test` skill
- **Lint/Format:** `uv run ruff check .` and `uv run ruff format .`
- **Type check:** `uv run mypy .`
- **Rebuild frontend:** `cd frontend && npm install && npm run build`
  (Node 18+; outputs the committed bundle to `src/bizkit/api/static/`.
  End users need no Node.)

## Hard Constraints
- **Target DBs are written only by `BaseBackend.apply()` on an APPROVED
  changeset.** No API route, CLI command, or service may write to a target
  database directly. `dry_run()` must leave the target unchanged.
- **All state transitions go through `WorkflowService`** (which delegates to
  `Changeset.transition()`). Never mutate a changeset's status via a
  repository update.
- **Every state transition writes exactly one `AuditEvent` in the same store
  transaction.** Audit is never best-effort or after-commit.
- **Every workflow action is authorized through the `AccessPolicy` port**
  (rights scoped per table/target). Services never embed role logic or
  bypass the port.
- **Maker ≠ checker** is enforced in the domain layer, not just the API —
  and no access policy adapter, role, or admin flag can override it. The
  sole relaxation is the `allow_self_approval` config setting (spec
  D26/D27): global `workflow.allow_self_approval` (default false) with an
  optional tri-state per-table override that inherits when unset — all
  config-file-only, git-reviewed, never toggleable at runtime.
  Self-approvals are conspicuously audited, never hidden, and
  `bizkit config validate` reports the effective posture per table.
- **bizkit never stores or verifies credentials.** Identity always arrives
  from outside (CLI flag, API auth middleware); bizkit decides entitlements
  only. Role/group claims used for enforcement come from the verified
  server-side channel — never from client-supplied data; frontend-known
  roles are UX affordances only (spec D25). Every `AuthProvider` mode
  (spec D42) either delegates verification externally (`oidc`, `ldap`)
  or involves no human credential at all (`token`) — a bizkit-owned
  username/password store is explicitly rejected. The trusted-header
  `none` mode must be **structurally impossible to reach in production**:
  `create_app()` refuses to start with `auth.provider: none` unless
  `auth.allow_insecure_dev_mode: true` is also set.
- **Validation runs at submit AND again immediately before apply** — target
  state may drift between approval and apply.
- **Validation rules are declarative data** (serializable pydantic models),
  never arbitrary code or `eval`.
- **Optional drivers stay lazy-imported** — `import bizkit` must succeed with
  only core dependencies installed.
- **Dependencies:** Do not add new libraries to `pyproject.toml` without
  asking.

## Rules & Coding Conventions
- **Style:** Follow PEP 8. Use `ruff` for all formatting.
- **Types:** Strict type hinting for all function signatures; mypy strict.
- **Docstrings:** Google-style for all public modules and functions.
- **Imports:** Standard library, third-party, then local modules.
- **Error Handling:** Custom exception classes rooted at `BizkitError`;
  never use bare `except:`.
- **Global State:** No globals; use dependency injection / config objects
  (`BizkitConfig`).
- **Tests:** In `/tests`, mirroring `src/`. pytest fixtures for
  setup/teardown. Unit tests never need a real database (in-memory SQLite for
  the store, mocks for backends). Integration tests sit behind markers
  (`integration`, `db_postgres`, `db_mysql`, `db_mssql`, `db_oracle`,
  `db_snowflake`, `db_databricks`, `slow`).

## Definition of Done
A change is done only when ALL of these hold (CI enforces them once the
pipeline lands):
- `uv run pytest` green, including new tests written first (TDD) —
  invariant changes extend the relevant matrix tests.
- `uv run ruff check .`, `uv run ruff format --check .`, and
  `uv run mypy .` (strict) all clean.
- Design touched? The `record-decision` skill was run — spec, CLAUDE.md,
  agents, and skills are in sync (spec §14).
- Frontend touched? `npm run build` green and the committed bundle in
  `src/bizkit/api/static/` is fresh.
- Runtime behavior touched? Verified end-to-end (run-stack smoke or
  /verify), not just unit-tested.

## Git & Workflow
- Semantic commits (`feat:`, `fix:`, `docs:`, …).
- Branch naming: `feature/name` or `fix/name`.
- Never auto-merge feature branches locally; create a PR and merge that.
