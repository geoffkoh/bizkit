---
name: add-backend
description: Checklist for adding or modifying a target database backend (dialect adapter) in bizkit. Use when wiring a new database technology or reworking an existing adapter's extras, type mapping, or tests.
disable-model-invocation: false
argument-hint: "<backend-name>"
---

# Add / Modify a Target Backend

Work through this checklist in order. Prefer delegating the implementation to the `db-dialect-specialist` agent.

## 1. Dependency approval

- Identify the SQLAlchemy dialect package and driver for the backend.
- **Ask the user before adding it** — new libraries never enter `pyproject.toml` without approval.
- Add it under `[project.optional-dependencies]` as `bizkit[<backend-name>]` and include it in the `all` extra.

## 2. Adapter module

- Create `src/bizkit/backends/<backend-name>.py` subclassing `BaseBackend`.
- The driver import must be lazy (inside a function/`__init__`), raising `BackendNotInstalledError` with the exact hint: `pip install 'bizkit[<backend-name>]'`.
- Implement/override: connection URL construction, `introspect_table()`, `dry_run()`, `apply()`.
- Document the dialect's quirks in the module docstring: transaction model (transactional DDL? implicit commits?), constraint enforcement, identifier quoting and case folding, NULL/empty-string handling, upsert/MERGE syntax.

## 3. Registration & type map

- Register the backend name in `src/bizkit/backends/registry.py` (lazy import path, not a direct import).
- Extend `src/bizkit/backends/typemap.py` in **both directions** (canonical → dialect, dialect → canonical).

## 4. Tests

- Unit tests in `tests/test_backends/` with mocked engine — these run in the fast suite with no driver installed.
- Integration tests marked `@pytest.mark.db_<backend-name>` and `@pytest.mark.integration`.
- Register the new marker in `pyproject.toml` `[tool.pytest.ini_options] markers`.
- Add the backend to the matrix table in the `db-matrix-test` skill (container image, or env-var gate if no container exists).

## 5. Documentation

- Add a row to the backend table in `CLAUDE.md`.
- Add the extra to the README install matrix.

## 6. Verify

```bash
uv sync --extra <backend-name>
uv run pytest                       # fast suite, driver-less path still green
uv run pytest -m db_<backend-name>  # if a live/containerized instance is available
uv run ruff check . && uv run mypy .
uv run python -c "import bizkit"    # core import works WITHOUT the extra too
```

The last check matters: uninstall path (`uv sync` without the extra) must still import cleanly and raise `BackendNotInstalledError` only on use.
