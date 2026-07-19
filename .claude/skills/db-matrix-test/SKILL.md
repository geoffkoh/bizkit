---
name: db-matrix-test
description: Run the bizkit backend integration test matrix, using containers where possible and env-var-gated live connections for cloud warehouses. Use when integration-testing one or all target database backends.
disable-model-invocation: false
argument-hint: "[backend|all]"
---

# Backend Integration Test Matrix

The fast suite (`uv run pytest`) never needs a real database. This skill runs the marked integration tests against real backends.

## Prerequisites

- Docker running (for containerized backends).
- `testcontainers` in the dev dependencies. If it is not installed yet, **ask the user before adding it** (dependency rule), then add to `[dependency-groups] dev`.
- The relevant extra installed, e.g. `uv sync --extra postgres`.

## The matrix

| Backend | Marker | How | Notes |
|---|---|---|---|
| PostgreSQL | `db_postgres` | container `postgres:17` | Reference implementation; run this first |
| MySQL + Percona | `db_mysql` | container `percona:8` | Percona image deliberately — it proves the "Percona rides the MySQL dialect" claim |
| MSSQL | `db_mssql` | container `mcr.microsoft.com/mssql/server:2022-latest` | Developer edition; needs `ACCEPT_EULA=Y`, ~2 GB RAM |
| Oracle | `db_oracle` | container `gvenzl/oracle-free` | Slow startup — also marked `slow` |
| Snowflake | `db_snowflake` | **no container** | Runs only if `BIZKIT_TEST_SNOWFLAKE_URL` is set; auto-skips otherwise |
| Databricks | `db_databricks` | **no container** | Runs only if `BIZKIT_TEST_DATABRICKS_URL` is set; auto-skips otherwise |

## Commands

```bash
# One backend
uv sync --extra postgres
uv run pytest -m db_postgres

# All containerizable backends (skips cloud ones without env vars)
uv sync --all-extras
uv run pytest -m integration

# Everything except slow (Oracle)
uv run pytest -m "integration and not slow"

# Cloud warehouses (read-only test schemas; never point at production)
BIZKIT_TEST_SNOWFLAKE_URL='snowflake://...' uv run pytest -m db_snowflake
BIZKIT_TEST_DATABRICKS_URL='databricks://...' uv run pytest -m db_databricks

# Confirm the default suite stays DB-free
uv run pytest -m "not integration"
```

## Rules

- Markers are registered in `pyproject.toml` `[tool.pytest.ini_options] markers`; a typo'd marker is an error, not a silent skip.
- Cloud-warehouse tests must target disposable test schemas and clean up after themselves.
- A failure on one backend is fixed matrix-wide: check whether the same behavior is asserted for the other six before patching one adapter (see `db-dialect-specialist` agent).
