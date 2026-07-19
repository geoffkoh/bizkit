---
name: record-decision
description: Record a bizkit design decision in SPECIFICATION.md's decision log and propagate it through CLAUDE.md, agents, and skills per the §14 maintenance protocol. Use whenever a design choice is made, changed, or superseded.
disable-model-invocation: false
argument-hint: "<short decision summary>"
---

# Record a Design Decision

`SPECIFICATION.md` is the source of truth (§14). This skill turns its
maintenance protocol into a checklist. Work through it **in order and in
the same change** — a decision is not "recorded" until every step is done.

## 1. Write the D-entry

- Append a new row to §2 Decision Log with the next number (D28, D29, …).
- **Never rewrite history**: if this changes an earlier decision, say
  "(refines DXX)" or "(supersedes DXX)" in the new entry and leave the old
  row untouched.
- The row needs: the decision itself (concrete — names, defaults, shapes),
  and the rationale (why this over the alternatives that were considered).
- If an alternative was seriously evaluated and rejected (e.g. D24 vs
  Next.js), record the rejection and the revisit condition.

## 2. Update the affected spec sections

Walk §3–§12 and fix every section the decision touches: domain model
fields, state machine (Mermaid diagram AND textual form — keep them
identical), enforcement-points table (§3.3), ER diagram (§3.10),
module layout (§4), backends (§5), services (§6), API (§7), CLI (§8),
configuration + workspace example (§9), frontend (§10), testing (§11),
dependencies (§12 — new libraries need explicit user approval).

## 3. Sync the Claude configuration

- `CLAUDE.md`: glossary, state machine block, layering, commands,
  **Hard Constraints** — whichever the decision touches.
- `.claude/agents/*.md`: for each affected agent, update the frontmatter
  `description` AND the body (ownership, invariants, checklists,
  anti-patterns). Check all of them: workflow-engineer,
  db-dialect-specialist, validation-engineer, frontend-engineer.
- `.claude/skills/*/SKILL.md`: same for add-backend, db-matrix-test,
  run-stack, and this skill.

## 4. Update implementation status

- §13: if the decision invalidates already-written code, add/extend the
  ⚠️ divergence note naming the files and what must change. If it only
  affects unwritten modules, ensure the module is listed as specified.

## 5. Self-check before finishing

- [ ] New D-row present, numbered correctly, cross-referenced from every
      section edited in steps 2–3 ("(DXX)" markers).
- [ ] Mermaid diagrams and textual forms agree.
- [ ] No section still states the superseded behavior.
- [ ] `README.md` still accurate (state machine, install, quickstart).
- [ ] If code and spec now disagree, §13 says so explicitly.
