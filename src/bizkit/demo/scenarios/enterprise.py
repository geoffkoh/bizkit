"""The `enterprise` scenario — two targets, cross-table rules, full lifecycle.

Deliberately covers what `sample` cannot (spec D45):

* **Two target profiles** (`risk`, `crm`), so the sidebar's backend grouping
  and per-backend grants are exercised rather than assumed.
* **Cross-table rules**, absent from `sample` entirely — including one that
  is **cross-backend** (`crm/coverage.desk` must exist in `risk/desks`),
  which is the case D44's lazy per-referenced-table resolution exists for.
* **APPLIED and FAILED**, reached by actually calling apply during seeding:
  one changeset lands its row in the target, another is approved against a
  row that already exists so the apply trips the primary key. `sample` stops
  at APPROVED and so never shows the write path or the retry affordance.
* **A rework across revisions**: rejected at revision 1, reworked,
  resubmitted as revision 2, then approved — so approvals visibly bind to
  the revision reviewed (D20).
* **Narrow grants**: a checker scoped to a single table, a reader across
  both backends, a maker holding rights on two backends, and an admin —
  instead of `sample`'s uniform `*/*/*`.
* **A deliberately invalid draft**, left in DRAFT so submitting it in the UI
  demonstrates a blocking cross-table validation report (D12). It cannot be
  seeded any further along: submit refuses invalid work.
"""

from pathlib import Path

from bizkit.demo.model import SeedContext, TargetTable
from bizkit.domain.changeset import ChangeItem, ChangeOp
from bizkit.exceptions import BizkitError

RISK_TABLES: list[TargetTable] = [
    TargetTable(
        name="desks",
        ddl=(
            "CREATE TABLE IF NOT EXISTS desks "
            "(desk TEXT PRIMARY KEY, region TEXT NOT NULL, head TEXT NOT NULL)"
        ),
        columns=("desk", "region", "head"),
        # MACRO exists here but NOT in trading_limits, so the seeded APPLIED
        # changeset can insert its limit and satisfy the cross-table rule.
        rows=[
            ("FX", "APAC", "T. Wu"),
            ("RATES", "EMEA", "L. Ortiz"),
            ("CREDIT", "AMER", "J. Silva"),
            ("EQUITY", "EMEA", "M. Haas"),
            ("MACRO", "AMER", "P. Adeyemi"),
        ],
    ),
    TargetTable(
        name="trading_limits",
        ddl=(
            "CREATE TABLE IF NOT EXISTS trading_limits "
            '(desk TEXT PRIMARY KEY, "limit" REAL NOT NULL, '
            "currency TEXT NOT NULL DEFAULT 'USD')"
        ),
        columns=("desk", "limit", "currency"),
        rows=[
            ("FX", 2_000_000, "USD"),
            ("RATES", 5_000_000, "USD"),
            ("CREDIT", 1_000_000, "USD"),
            ("EQUITY", 3_000_000, "USD"),
        ],
    ),
    TargetTable(
        name="holidays",
        ddl=(
            "CREATE TABLE IF NOT EXISTS holidays "
            "(day TEXT PRIMARY KEY, name TEXT NOT NULL, market TEXT NOT NULL)"
        ),
        columns=("day", "name", "market"),
        # 2026-12-25 is present on purpose: the FAILED changeset re-inserts it.
        rows=[
            ("2026-12-25", "Christmas Day", "ALL"),
            ("2026-08-09", "National Day", "SG"),
            ("2026-07-04", "Independence Day", "US"),
        ],
    ),
    TargetTable(
        name="risk_params",
        ddl=(
            "CREATE TABLE IF NOT EXISTS risk_params "
            "(param TEXT PRIMARY KEY, value TEXT NOT NULL)"
        ),
        columns=("param", "value"),
        rows=[("var_confidence", "0.99"), ("stress_scenarios", "12")],
    ),
]

CRM_TABLES: list[TargetTable] = [
    TargetTable(
        name="client_tiers",
        ddl=(
            "CREATE TABLE IF NOT EXISTS client_tiers "
            "(tier TEXT PRIMARY KEY, min_aum REAL NOT NULL, "
            "discount_bps INTEGER NOT NULL)"
        ),
        columns=("tier", "min_aum", "discount_bps"),
        # PLATINUM is absent: the rework changeset introduces it.
        rows=[
            ("BRONZE", 0, 0),
            ("SILVER", 1_000_000, 5),
            ("GOLD", 10_000_000, 12),
        ],
    ),
    TargetTable(
        name="fee_schedules",
        ddl=(
            "CREATE TABLE IF NOT EXISTS fee_schedules "
            "(schedule_id TEXT PRIMARY KEY, tier TEXT NOT NULL, "
            "fee_bps INTEGER NOT NULL)"
        ),
        columns=("schedule_id", "tier", "fee_bps"),
        rows=[
            ("FS-BRONZE", "BRONZE", 40),
            ("FS-SILVER", "SILVER", 32),
            ("FS-GOLD", "GOLD", 25),
        ],
    ),
    TargetTable(
        name="coverage",
        ddl=(
            "CREATE TABLE IF NOT EXISTS coverage "
            "(client_id TEXT PRIMARY KEY, desk TEXT NOT NULL, tier TEXT NOT NULL)"
        ),
        columns=("client_id", "desk", "tier"),
        rows=[("C-1001", "FX", "GOLD"), ("C-1002", "RATES", "SILVER")],
    ),
    TargetTable(
        name="comms_prefs",
        ddl=(
            "CREATE TABLE IF NOT EXISTS comms_prefs "
            "(client_id TEXT PRIMARY KEY, channel TEXT NOT NULL, "
            "opted_in INTEGER NOT NULL)"
        ),
        columns=("client_id", "channel", "opted_in"),
        rows=[("C-1001", "email", 1), ("C-1002", "phone", 0)],
    ),
]


def workspace(store_url: str, targets: dict[str, Path]) -> dict[str, object]:
    """Two target profiles, eight tables, all four rule kinds."""
    return {
        "version": 1,
        "store_url": store_url,
        "targets": {
            "risk": {"backend": "sqlite", "url": f"sqlite:///{targets['risk']}"},
            "crm": {"backend": "sqlite", "url": f"sqlite:///{targets['crm']}"},
        },
        "workflow": {"allow_self_approval": False},
        "tables": [
            {
                "backend": "risk",
                "table": "desks",
                "rules": [
                    {
                        "kind": "constraint",
                        "rule_id": "region-known",
                        "column": "region",
                        "allowed_values": ["AMER", "EMEA", "APAC"],
                        "description": "Region must be a booking region",
                    },
                    {
                        "kind": "cross_field",
                        "rule_id": "desk-complete",
                        "columns": ["desk", "region", "head"],
                        "predicate": "all-present",
                        "description": "A desk needs a code, region, and head",
                    },
                ],
            },
            {
                "backend": "risk",
                "table": "trading_limits",
                "review_ttl": 604800,
                "apply_ttl": 172800,
                "max_changeset_items": 50,
                "rules": [
                    {
                        "kind": "cross_table",
                        "rule_id": "desk-registered",
                        "ref_table": {"backend": "risk", "table": "desks"},
                        "local_columns": ["desk"],
                        "ref_columns": ["desk"],
                        "must_exist": True,
                        "description": "A limit may only be set for a registered desk",
                    },
                    {
                        "kind": "constraint",
                        "rule_id": "limit-range",
                        "column": "limit",
                        "min_value": 0,
                        "max_value": 10000000,
                        "description": "Limits are 0–10M",
                    },
                    {
                        "kind": "constraint",
                        "rule_id": "currency-allowed",
                        "column": "currency",
                        "allowed_values": ["USD", "EUR", "SGD", "JPY"],
                        "description": "Only approved settlement currencies",
                    },
                ],
            },
            {
                "backend": "risk",
                "table": "holidays",
                "review_ttl": 259200,
                "apply_ttl": 86400,
                "rules": [
                    {
                        "kind": "constraint",
                        "rule_id": "market-known",
                        "column": "market",
                        "allowed_values": ["ALL", "SG", "US", "UK", "JP"],
                        "description": "Market must be a supported venue",
                    },
                    {
                        "kind": "cross_field",
                        "rule_id": "day-iso",
                        "columns": ["day"],
                        "predicate": "date-is-iso",
                        "description": "Day must be an ISO date (YYYY-MM-DD)",
                    },
                ],
            },
            {
                "backend": "risk",
                "table": "risk_params",
                # Lapsed review window so a seeded changeset shows EXPIRED (D21).
                "review_ttl": -3600,
                "rules": [],
            },
            {
                "backend": "crm",
                "table": "client_tiers",
                "review_ttl": 604800,
                "rules": [
                    {
                        "kind": "constraint",
                        "rule_id": "aum-non-negative",
                        "column": "min_aum",
                        "min_value": 0,
                        "not_null": True,
                        "description": "Minimum AUM must be present and non-negative",
                    },
                    {
                        "kind": "type",
                        "rule_id": "discount-integer",
                        "column": "discount_bps",
                        "expected_type": "integer",
                        "description": "Discount is whole basis points",
                    },
                ],
            },
            {
                "backend": "crm",
                "table": "fee_schedules",
                "rules": [
                    {
                        "kind": "cross_table",
                        "rule_id": "tier-exists",
                        "ref_table": {"backend": "crm", "table": "client_tiers"},
                        "local_columns": ["tier"],
                        "ref_columns": ["tier"],
                        "must_exist": True,
                        "description": "A fee schedule must reference a defined tier",
                    },
                    {
                        "kind": "constraint",
                        "rule_id": "fee-range",
                        "column": "fee_bps",
                        "min_value": 0,
                        "max_value": 100,
                        "description": "Fees are 0–100 bps",
                    },
                ],
            },
            {
                "backend": "crm",
                "table": "coverage",
                "rules": [
                    {
                        # Cross-*backend*: the referenced table lives in `risk`.
                        # Resolution is per referenced table (D44), so this is
                        # an ordinary rule, not a special case.
                        "kind": "cross_table",
                        "rule_id": "desk-registered-cross-backend",
                        "ref_table": {"backend": "risk", "table": "desks"},
                        "local_columns": ["desk"],
                        "ref_columns": ["desk"],
                        "must_exist": True,
                        "description": "Coverage desk must exist in the risk desk registry",
                    },
                    {
                        "kind": "cross_table",
                        "rule_id": "coverage-tier-exists",
                        "ref_table": {"backend": "crm", "table": "client_tiers"},
                        "local_columns": ["tier"],
                        "ref_columns": ["tier"],
                        "must_exist": True,
                        "description": "Coverage tier must be a defined tier",
                    },
                ],
            },
            {
                "backend": "crm",
                "table": "comms_prefs",
                # Demo of D26/D27: routine opt-in flips may be self-approved.
                "allow_self_approval": True,
                "rules": [
                    {
                        "kind": "constraint",
                        "rule_id": "channel-known",
                        "column": "channel",
                        "allowed_values": ["email", "phone", "post", "none"],
                        "description": "Channel must be a supported contact method",
                    }
                ],
            },
        ],
        "grants": [
            # Backend-wide maker/checker pairs.
            {"principal": "alice", "role": "maker", "scope": "risk/*/*"},
            {"principal": "bob", "role": "checker", "scope": "risk/*/*"},
            {"principal": "carol", "role": "maker", "scope": "crm/*/*"},
            {"principal": "erin", "role": "checker", "scope": "crm/*/*"},
            # Narrow scope: frank checks one table, nothing else.
            {"principal": "frank", "role": "checker", "scope": "risk/*/trading_limits"},
            # carol self-approves comms_prefs, which needs BOTH: `approve`
            # rights on that table AND the table's allow_self_approval. The
            # setting relaxes four-eyes (D26/D27); it never grants the action.
            {"principal": "carol", "role": "checker", "scope": "crm/*/comms_prefs"},
            # A maker who works across both backends.
            {"principal": "heidi", "role": "maker", "scope": "risk/*/*"},
            {"principal": "heidi", "role": "maker", "scope": "crm/*/*"},
            # Reader/auditor across everything (D38/D43).
            {"principal": "dave", "role": "reader", "scope": "risk/*/*"},
            {"principal": "dave", "role": "reader", "scope": "crm/*/*"},
            {"principal": "grace", "role": "admin", "scope": "*/*/*"},
        ],
    }


def populate(ctx: SeedContext) -> None:  # noqa: PLR0915 - a demo script, read top to bottom
    """Ten changesets spanning every state, including APPLIED and FAILED."""
    service = ctx.workflow
    comments = ctx.comments
    limits = ctx.ref("risk", "trading_limits")
    desks = ctx.ref("risk", "desks")
    holidays = ctx.ref("risk", "holidays")
    params = ctx.ref("risk", "risk_params")
    tiers = ctx.ref("crm", "client_tiers")
    fees = ctx.ref("crm", "fee_schedules")
    coverage = ctx.ref("crm", "coverage")
    prefs = ctx.ref("crm", "comms_prefs")

    # 1. APPLIED — the full lifecycle, ending with a real write to the target.
    #    MACRO is a registered desk but has no limit yet, so the cross-table
    #    rule passes and the insert cannot collide.
    applied = service.create(
        limits,
        maker="alice",
        title="Set MACRO desk limit",
        description="New desk stood up this quarter; limit per risk committee.",
        items=[
            ChangeItem(
                op=ChangeOp.INSERT,
                values={"desk": "MACRO", "limit": 1_250_000, "currency": "USD"},
            )
        ],
    )
    service.submit(applied.id, "alice")
    service.approve(applied.id, "bob", reason="Matches committee minutes 2026-Q3")
    outcome = service.apply(applied.id, "bob")
    if not outcome.ok:  # pragma: no cover - a broken scenario must be loud
        raise BizkitError(f"seed: MACRO limit should have applied: {outcome.error}")

    # 2. FAILED — approved against a day that already exists, so apply trips
    #    the primary key. Shows the failure path and the Retry affordance.
    failing = service.create(
        holidays,
        maker="alice",
        title="Add Christmas Day 2026",
        description="Calendar roll — this one collides with an existing row.",
        items=[
            ChangeItem(
                op=ChangeOp.INSERT,
                values={"day": "2026-12-25", "name": "Christmas Day", "market": "ALL"},
            )
        ],
    )
    service.submit(failing.id, "alice")
    service.approve(failing.id, "bob", reason="Looks routine")
    outcome = service.apply(failing.id, "bob")
    if outcome.ok:  # pragma: no cover
        raise BizkitError("seed: duplicate holiday should have failed to apply")

    # 3. REJECTED -> rework -> resubmitted as revision 2 -> APPROVED.
    #    The rejection is about justification rather than content, so the
    #    resubmission is the same items at a new revision — which is exactly
    #    what revision binding has to handle (D20).
    reworked = service.create(
        tiers,
        maker="carol",
        title="Introduce PLATINUM tier",
        description="Top-tier bracket for the private-bank book.",
        items=[
            ChangeItem(
                op=ChangeOp.INSERT,
                values={"tier": "PLATINUM", "min_aum": 50_000_000, "discount_bps": 20},
            )
        ],
    )
    service.submit(reworked.id, "carol")
    service.reject(
        reworked.id, "erin", reason="Needs the pricing committee reference in the notes"
    )
    service.rework(reworked.id, "carol")
    comments.add_comment(
        reworked.id, "carol", "Pricing committee ref PC-2026-114, minuted 2026-07-02."
    )
    service.submit(reworked.id, "carol")
    service.approve(reworked.id, "erin", reason="Reference supplied; approved at rev 2")

    # 4. DRAFT (valid) — ready for the reader to inspect and the maker to submit.
    service.create(
        fees,
        maker="carol",
        title="Trim GOLD fee to 22bps",
        description="Competitive review; still gathering sign-off.",
        items=[
            ChangeItem(
                op=ChangeOp.UPDATE,
                key={"schedule_id": "FS-GOLD"},
                values={"fee_bps": 22},
            )
        ],
    )

    # 5. DRAFT (deliberately invalid) — submitting this in the UI produces a
    #    blocking cross-backend cross-table report. It cannot be seeded past
    #    DRAFT, because submit refuses invalid work (D12).
    service.create(
        coverage,
        maker="heidi",
        title="Assign C-1003 to the SYNTHETICS desk",
        description="Intentionally invalid: SYNTHETICS is not a registered "
        "risk desk, so submitting this shows a cross-backend "
        "cross-table validation failure.",
        items=[
            ChangeItem(
                op=ChangeOp.INSERT,
                values={"client_id": "C-1003", "desk": "SYNTHETICS", "tier": "GOLD"},
            )
        ],
    )

    # 6. SUBMITTED with a comment thread, awaiting bob.
    pending = service.create(
        desks,
        maker="alice",
        title="Register COMMODITIES desk",
        description="Desk approved by the exec committee; registry entry first.",
        items=[
            ChangeItem(
                op=ChangeOp.INSERT,
                values={"desk": "COMMODITIES", "region": "EMEA", "head": "R. Novak"},
            )
        ],
    )
    service.submit(pending.id, "alice")
    question = comments.add_comment(
        pending.id, "bob", "Is R. Novak confirmed as head, or acting?"
    )
    comments.add_comment(
        pending.id, "alice", "Confirmed from 1 August.", parent_id=question.id
    )

    # 7. EXPIRED — risk_params has a lapsed review window.
    stale = service.create(
        params,
        maker="alice",
        title="Raise VaR confidence to 99.5%",
        items=[
            ChangeItem(
                op=ChangeOp.UPDATE,
                key={"param": "var_confidence"},
                values={"value": "0.995"},
            )
        ],
    )
    service.submit(stale.id, "alice")
    service.expire_overdue()

    # 8. WITHDRAWN — the maker changed their mind before review.
    withdrawn = service.create(
        limits,
        maker="alice",
        title="Cut EQUITY limit",
        items=[
            ChangeItem(
                op=ChangeOp.UPDATE, key={"desk": "EQUITY"}, values={"limit": 2_000_000}
            )
        ],
    )
    service.withdraw(withdrawn.id, "alice")

    # 9. SELF-APPROVED — comms_prefs permits it (D26/D27); conspicuously audited.
    solo = service.create(
        prefs,
        maker="carol",
        title="Opt C-1002 back into phone contact",
        description="Routine opt-in flip; this table permits self-approval.",
        items=[
            ChangeItem(
                op=ChangeOp.UPDATE, key={"client_id": "C-1002"}, values={"opted_in": 1}
            )
        ],
    )
    service.submit(solo.id, "carol")
    service.approve(solo.id, "carol")

    # 10. SUBMITTED on the one table frank can check — exercises narrow scope.
    narrow = service.create(
        limits,
        maker="heidi",
        title="Raise CREDIT limit to 1.4M",
        description="Only frank (scoped to this table) and bob can review this.",
        items=[
            ChangeItem(
                op=ChangeOp.UPDATE, key={"desk": "CREDIT"}, values={"limit": 1_400_000}
            )
        ],
    )
    service.submit(narrow.id, "heidi")

    ctx.note(
        "2 targets (risk, crm), 8 tables, all four rule kinds incl. a "
        "cross-BACKEND cross-table rule (crm/coverage.desk -> risk/desks)"
    )
    ctx.note(
        "10 changesets covering every state: one APPLIED (row written to "
        "risk_target.db), one FAILED (duplicate key, retryable), a "
        "reject->rework->approve at revision 2, a self-approved one, an "
        "EXPIRED one, and a deliberately invalid DRAFT that shows a "
        "cross-table validation report when you submit it"
    )
    ctx.note(
        "principals — makers alice (risk), carol (crm), heidi (both); "
        "checkers bob (risk), erin (crm), frank (risk/trading_limits only), "
        "carol (crm/comms_prefs only, for the self-approval demo); "
        "reader dave (both); admin grace"
    )
