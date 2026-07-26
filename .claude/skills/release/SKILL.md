---
name: release
description: Cut a bizkit release — preflight quality gates, semver bump, changelog, frontend bundle freshness, migration check, wheel build and smoke-install, tag. Use when the user asks to release, tag, or publish a version.
disable-model-invocation: false
argument-hint: "[major|minor|patch]"
---

# Release bizkit

Application teams consume releases, not branches. Work top to bottom; any
failure stops the release.

## 1. Preflight

- Working tree clean, on `main` (or a `release/x.y` branch), up to date
  with remote.
- Run the `spec-conformance` skill (scoped to changes since the last tag
  at minimum); no unreconciled divergences.
- Quality gates: `uv run pytest`, `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run mypy .` — all clean.
- Frontend gates: `cd frontend && npx tsc -b && npm test` (vitest) — clean.
- `uv run bizkit config schema` succeeds (workspace schema generable).

## 2. Version and changelog

- Semver: **major** = breaking library API, `/api/vN` bump, or workspace
  config `version` bump (D23); **minor** = new backward-compatible
  features/decisions; **patch** = fixes only.
- Bump `version` in `pyproject.toml` and `src/bizkit/__init__.py`
  (`__version__`) — keep them identical.
- Update `CHANGELOG.md` (Keep-a-Changelog format): move Unreleased →
  the new version with date; reference relevant D-numbers.

## 3. Frontend bundle freshness

- `cd frontend && npm ci && npm run build` — the committed bundle in
  `src/bizkit/api/static/` must equal the rebuild output (`git status`
  clean afterwards). A dirty diff means someone changed the SPA without
  rebuilding: commit the fresh bundle first.

## 4. Store migrations (D34)

- Pre-GA: confirm `metadata.create_all` path still documented dev-only.
- Post-GA: `alembic upgrade head` green on (a) a fresh store and (b) a
  store created from the previous release; any store-schema change since
  the last tag must have a migration.

## 5. Build and smoke-install

```bash
uv build
# wheel must contain py.typed and api/static/
python -m venv /tmp/bizkit-smoke && /tmp/bizkit-smoke/bin/pip install dist/bizkit-*.whl
/tmp/bizkit-smoke/bin/bizkit --help
/tmp/bizkit-smoke/bin/python -c "import bizkit; print(bizkit.__version__)"
```

Core install must import with zero optional drivers (D3).

## 6. Tag and publish

- Commit as `chore: release vX.Y.Z`, tag `vX.Y.Z`, push via the normal
  PR-first flow — never merge locally.
- Publishing (PyPI or internal index) is a separate explicit step:
  **ask the user before publishing**; `uv publish` once confirmed.
