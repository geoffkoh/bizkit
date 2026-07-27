---
name: spec-conformance
description: Audit the bizkit codebase against SPECIFICATION.md — verify every decided feature is implemented, tested, and unchanged, and report divergences. Use before releases, after large changes, or when resuming work after a gap.
disable-model-invocation: false
argument-hint: "[section|decision e.g. D21]"
---

# Spec Conformance Audit

`SPECIFICATION.md` is the source of truth. This audit answers: *does the
code actually implement what was decided, at the agreed quality?* Run it
scoped (one D-entry or section) or full.

## 1. Build the checklist from the spec

- Read §2 (Decision Log) and §13 (Implementation Status).
- For a scoped run, collect the named decision plus everything it
  references; for a full run, walk D1 upward.
- §13's ⚠️ divergence notes are known debts — verify they are still
  accurate, not resolved-but-stale or grown-worse.

## 2. Verify each decision against the code

For every in-scope decision, locate the implementing code and classify:

- **Conformant** — implemented as specified, with tests.
- **Divergent** — implemented differently than specified. Name file, line,
  and the exact disagreement.
- **Unimplemented** — specified, absent, and not flagged in §13.
- **Undocumented** — behavior in code with no spec basis (reverse
  divergence; someone skipped `record-decision`).

## 3. Verify the invariant tests exist and bite

The controls are only real if a test fails when they break. Check for:

- Transition matrix: every (state, target) pair, legal and illegal (D9/D20/D21).
- Four-eyes: strict default AND the D26/D27 effective-setting matrix.
- Authorization: allow and deny per operation, scope wildcard matching (D5/D27).
- Audit: exactly-once per transition, same transaction, append-only (D10/D31/D35).
- Revision binding: approvals/validation bound to the reviewed revision (D20).
- Concurrency: racing transitions — one winner, `ConcurrencyError` loser,
  single audit event (D31).
- Lazy imports: core imports and fast suite pass with zero drivers (D3).
- Store upgrades (D45): populated store survives `upgrade head` with rows
  intact; app refuses to start when behind *or* ahead of head; no
  `create_all` remains on any production path; `alembic check` reports no
  drift between `store/models.py` and the migration chain.

## 4. Verify the quality gates

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy .
```

All clean, plus: CLAUDE.md Definition of Done obligations met for recent
changes; agents/skills descriptions match current spec (§14).

## 5. Report and reconcile

- Produce a findings table: decision → status → evidence → action.
- Update §13 so it tells the truth (add/extend/remove ⚠️ notes).
- For divergences, propose per finding: fix the code, or run
  `record-decision` to change the spec explicitly. Never leave them
  silently disagreeing.
