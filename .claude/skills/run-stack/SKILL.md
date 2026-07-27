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
# Writes a sample workspace config (bizkit.workspace.json with a demo table, rules,
# and grants for maker "alice" / checker "bob" — file-first per spec D22),
# creates the SQLite workflow store, a sample SQLite *target* DB with a
# demo config table, and one pending changeset, so authorization and
# validation are exercised out of the box. The seeded config sets
# auth.provider: none with auth.allow_insecure_dev_mode: true (spec D42) —
# required or create_app()/CLI refuse to start; never set that flag
# outside a local/dev workspace file.
uv run bizkit init-store --seed-sample
uv run bizkit --config bizkit.workspace.json list   # sanity check
```

Files land in the current directory (`bizkit.workspace.json`, `bizkit.db`, `sample_target.db`) — run from a scratch directory or delete them afterwards; the `.db` files are gitignored.

`init-store` creates the schema by running the migrations to head (spec
D45). If you already have a `bizkit.db` from an earlier checkout, the
server will refuse to start with a revision mismatch — run `uv run bizkit
store upgrade` (or just delete the scratch `.db` and re-seed). `uv run
bizkit store current` shows where a store sits.

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
npm test           # vitest + React Testing Library (no server needed)
```

Requires Node 18+ (Vite 7 wants 20.19+/22.12+). If `node` is missing,
`pixi global install "nodejs>=22"` puts it on the PATH.

## 4. Smoke checks

```bash
curl -s http://127.0.0.1:8091/api/health | jq .    # liveness (unversioned)
curl -s http://127.0.0.1:8091/api/ready | jq .     # store + config ready
# Identity comes from outside bizkit; the dev middleware trusts these headers.
curl -s -H 'X-Bizkit-User: bob' http://127.0.0.1:8091/api/v1/changesets | jq .
```

Expect a healthy status and the seeded changeset in the list.

Apply an approved changeset (D44) — the seed leaves two APPROVED and ready:

```bash
ID=$(curl -s -H 'X-Bizkit-User: bob' http://127.0.0.1:8091/api/v1/changesets \
  | jq -r '[.[] | select(.state=="approved")][0].id')
# Rehearse first: exercises the target's constraints, then rolls back.
uv run bizkit --config bizkit.workspace.json apply "$ID" --actor bob --dry-run
uv run bizkit --config bizkit.workspace.json apply "$ID" --actor bob
```

`apply` is a **checker** right, so `--actor alice` (a maker) is correctly
refused with a 403/exit 1. In the UI the same action lives on the changeset
detail page behind a two-click confirmation. A target refusal comes back as
HTTP 200 with `ok: false` and the changeset in FAILED — that is the recorded
outcome, not a transport error.

## 5. Production-like variant

```bash
cd frontend && npm run build          # bundle → src/bizkit/api/static/
uv run bizkit serve                   # serves API + built SPA, no Vite needed
```

## 6. Teardown

Stop the background processes; remove `bizkit.db` / `sample_target.db` if created in the repo.
