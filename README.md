# bizkit

Business Configuration Toolkit — manage configuration data that lives in
database tables, with maker-checker change workflows, threaded commenting,
validation, and a full audit trail.

Configuration changes are drafted as **changesets** by a *maker*, validated,
reviewed and approved by a *checker*, and only then applied to the target
database. Every state transition is audited.

```
DRAFT → SUBMITTED → (APPROVED | REJECTED)
APPROVED → APPLIED | FAILED
REJECTED, FAILED → DRAFT      (rework by the maker)
FAILED → APPLIED              (retry of the approved revision)
SUBMITTED, APPROVED → EXPIRED (review/apply deadline lapses)
EXPIRED → DRAFT               (rework by the maker)
DRAFT, SUBMITTED → WITHDRAWN
```

Rejected, failed, or expired changesets route back to the maker for
adjustment; every resubmission is a new revision requiring fresh review,
so approvals always refer to the exact content reviewed. Configurable
per-table review and apply windows keep submissions from lingering and
stale approvals from being applied.

## Supported target databases

| Backend | Install extra |
|---|---|
| Oracle | `pip install 'bizkit[oracle]'` |
| MSSQL | `pip install 'bizkit[mssql]'` |
| MySQL / Percona | `pip install 'bizkit[mysql]'` |
| PostgreSQL | `pip install 'bizkit[postgres]'` |
| Snowflake | `pip install 'bizkit[snowflake]'` |
| Databricks | `pip install 'bizkit[databricks]'` |
| Everything | `pip install 'bizkit[all]'` |

Workflow state (changesets, approvals, comments, audit events) lives in
bizkit's own store — SQLite by default, PostgreSQL recommended for
production. Target databases are only ever written when an approved
changeset is applied.

## Quickstart

```bash
pip install bizkit                 # or: uv sync (from a checkout)

bizkit init-store --seed-sample    # create the workflow store + demo data
bizkit list                        # list changesets
bizkit serve                       # REST API + web UI on :8091
```

## Interfaces

- **Python library** — `import bizkit`
- **CLI** — `bizkit --help`
- **REST API** — `bizkit serve` (FastAPI on :8091)
- **Web UI** — React SPA served by the API (built bundle ships in the wheel)

## Development

```bash
uv sync                  # install with dev dependencies
uv run pytest            # fast suite (no databases needed)
uv run ruff check .      # lint
uv run ruff format .     # format
uv run mypy .            # type check (strict)
```

Integration tests against real databases are marked and skipped by default —
see `.claude/skills/db-matrix-test/SKILL.md`.

## License

GPL-3.0 — see [LICENSE](LICENSE).
