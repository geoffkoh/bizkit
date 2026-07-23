---
name: run-stack
description: Launch the bizkit dev stack for manual testing — seeded SQLite workflow store, FastAPI on :8091, and optionally the Vite dev server for the React UI. Use when the user wants to run, demo, or manually exercise the app.
disable-model-invocation: false
argument-hint: "[--no-frontend]"
---

# Run the bizkit Dev Stack

## 1. Install & seed

```bash
uv sync
# Writes a sample workspace config (bizkit.yaml with a demo table, rules,
# and grants for maker "alice" / checker "bob" — file-first per spec D22),
# creates the SQLite workflow store, a sample SQLite *target* DB with a
# demo config table, and one pending changeset, so authorization and
# validation are exercised out of the box. The seeded config sets
# auth.provider: none with auth.allow_insecure_dev_mode: true (spec D42) —
# required or create_app()/CLI refuse to start; never set that flag
# outside a local/dev workspace file.
uv run bizkit init-store --seed-sample
uv run bizkit --config bizkit.yaml list   # sanity check
```

Files land in the current directory (`bizkit.yaml`, `bizkit.db`, `sample_target.db`) — run from a scratch directory or delete them afterwards; the `.db` files are gitignored.

## 2. API server

```bash
uv run bizkit serve --reload   # FastAPI on http://127.0.0.1:8091
```

Run in the background when driving it from the same session. If a built SPA exists at `src/bizkit/api/static/`, it is served at `/`.

## 3. Frontend dev loop (skip with --no-frontend)

```bash
cd frontend
npm install
npm run dev        # Vite dev server, proxies /api → :8091
```

Requires Node 18+.

## 4. Smoke checks

```bash
curl -s http://127.0.0.1:8091/api/health | jq .    # liveness (unversioned)
curl -s http://127.0.0.1:8091/api/ready | jq .     # store + config ready
# Identity comes from outside bizkit; the dev middleware trusts these headers.
curl -s -H 'X-Bizkit-User: bob' http://127.0.0.1:8091/api/v1/changesets | jq .
```

Expect a healthy status and the seeded changeset in the list.

## 5. Production-like variant

```bash
cd frontend && npm run build          # bundle → src/bizkit/api/static/
uv run bizkit serve                   # serves API + built SPA, no Vite needed
```

## 6. Teardown

Stop the background processes; remove `bizkit.db` / `sample_target.db` if created in the repo.
