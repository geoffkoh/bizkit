"""The `sample` scenario — one target, five tables, every lifecycle state.

The default demo since the project's first commit, moved here unchanged
(spec D45). One target profile keeps the mental model small: five tables
covering each rule kind except cross-table, and eight changesets covering
every state a changeset can sit in without touching the target.

Nothing here is APPLIED — see the `enterprise` scenario for the full
lifecycle including a successful apply and a deliberate failure.
"""

from pathlib import Path

from bizkit.demo.model import SeedContext, TargetTable
from bizkit.domain.changeset import ChangeItem, ChangeOp

_ISSUERS = [
    "Meridian",
    "Northgate",
    "Solstice",
    "Harbourview",
    "Atlas",
    "Kestrel",
    "Blueline",
    "Pinnacle",
    "Redwood",
    "Crescent",
]
_KINDS = ["Bond", "Note", "Bill", "Perp", "FRN", "Linker"]
_CURRENCIES = ["USD", "EUR", "SGD", "JPY", "GBP", "CHF"]
_CLASSES = ["BOND", "EQUITY", "FX", "COMMODITY"]


def _instrument_rows() -> list[tuple[object, ...]]:
    """1,200 rows, enough to push the grid past its client-side fetch cap."""
    return [
        (
            f"XS{i:010d}",
            f"{_ISSUERS[i % len(_ISSUERS)]} {_KINDS[i % len(_KINDS)]} {2026 + i % 10}",
            _CURRENCIES[i % len(_CURRENCIES)],
            _CLASSES[i % len(_CLASSES)],
            0 if i % 17 == 0 else 1,
        )
        for i in range(1, 1201)
    ]


TABLES: list[TargetTable] = [
    TargetTable(
        name="fx_rates",
        ddl=(
            "CREATE TABLE IF NOT EXISTS fx_rates "
            "(pair TEXT PRIMARY KEY, rate REAL NOT NULL, "
            "source TEXT NOT NULL DEFAULT 'vendor')"
        ),
        columns=("pair", "rate", "source"),
        # Deliberately omits the pairs the seeded changesets insert (USDJPY,
        # USDSGD, USDCAD, EURGBP): a pending insert has to be for a row that
        # does not exist yet, or applying it trips the primary key. The
        # pending update (GBPUSD) does need its row present.
        rows=[
            ("EURUSD", 1.09, "vendor"),
            ("GBPUSD", 1.27, "vendor"),
            ("AUDUSD", 0.66, "vendor"),
            ("USDCHF", 0.88, "desk"),
            ("NZDUSD", 0.61, "vendor"),
            ("EURCHF", 0.96, "desk"),
            ("USDHKD", 7.81, "vendor"),
            ("USDCNH", 7.24, "vendor"),
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
            ("COMMODITIES", 1_500_000, "EUR"),
            ("EM", 750_000, "SGD"),
        ],
    ),
    TargetTable(
        name="holidays",
        ddl=(
            "CREATE TABLE IF NOT EXISTS holidays "
            "(day TEXT PRIMARY KEY, name TEXT NOT NULL, market TEXT NOT NULL)"
        ),
        columns=("day", "name", "market"),
        rows=[
            ("2026-12-25", "Christmas Day", "ALL"),
            ("2026-08-09", "National Day", "SG"),
            ("2026-07-04", "Independence Day", "US"),
            ("2026-01-01", "New Year's Day", "ALL"),
            ("2026-05-25", "Memorial Day", "US"),
            ("2026-12-26", "Boxing Day", "UK"),
            ("2026-02-17", "Chinese New Year", "SG"),
            ("2026-11-23", "Labour Thanksgiving", "JP"),
        ],
    ),
    TargetTable(
        name="instruments",
        ddl=(
            "CREATE TABLE IF NOT EXISTS instruments "
            "(isin TEXT PRIMARY KEY, name TEXT NOT NULL, "
            "currency TEXT NOT NULL, asset_class TEXT NOT NULL, "
            "active INTEGER NOT NULL DEFAULT 1)"
        ),
        columns=("isin", "name", "currency", "asset_class", "active"),
        rows=_instrument_rows(),
    ),
    TargetTable(
        name="legacy_params",
        ddl=(
            "CREATE TABLE IF NOT EXISTS legacy_params "
            "(param TEXT PRIMARY KEY, value TEXT NOT NULL)"
        ),
        columns=("param", "value"),
        rows=[
            ("legacy_mode", "off"),
            ("retry_count", "3"),
            ("eod_cutoff", "17:30"),
        ],
    ),
]


def workspace(store_url: str, targets: dict[str, Path]) -> dict[str, object]:
    """The workspace config for this scenario."""
    return {
        "version": 1,
        "store_url": store_url,
        "targets": {
            "sample": {"backend": "sqlite", "url": f"sqlite:///{targets['sample']}"}
        },
        "workflow": {"allow_self_approval": False},
        "tables": [
            {
                "backend": "sample",
                "table": "fx_rates",
                "rules": [
                    {
                        "kind": "constraint",
                        "rule_id": "rate-positive",
                        "column": "rate",
                        "min_value": 0,
                        "not_null": True,
                        "description": "Rates must be positive and present",
                    },
                    {
                        "kind": "type",
                        "rule_id": "rate-numeric",
                        "column": "rate",
                        "expected_type": "decimal",
                        "description": "Rate must be a decimal number",
                    },
                    {
                        "kind": "constraint",
                        "rule_id": "source-known",
                        "column": "source",
                        "allowed_values": ["vendor", "desk", "manual"],
                        "description": "Source must be a recognised feed",
                    },
                    {
                        "kind": "cross_field",
                        "rule_id": "pair-format",
                        "columns": ["pair"],
                        "predicate": "pair-is-6-uppercase",
                        "description": "Pair must be 6 uppercase letters (e.g. EURUSD)",
                    },
                ],
            },
            {
                "backend": "sample",
                "table": "trading_limits",
                "review_ttl": 604800,
                "apply_ttl": 172800,
                "max_changeset_items": 50,
                "rules": [
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
                "backend": "sample",
                "table": "holidays",
                "review_ttl": 259200,
                "apply_ttl": 86400,
                # Demo of D26/D27: this table permits self-approval.
                "allow_self_approval": True,
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
                "backend": "sample",
                "table": "instruments",
                "review_ttl": 604800,
                "rules": [
                    {
                        "kind": "constraint",
                        "rule_id": "asset-class-known",
                        "column": "asset_class",
                        "allowed_values": ["BOND", "EQUITY", "FX", "COMMODITY"],
                        "description": "Asset class must be recognised",
                    },
                    {
                        "kind": "cross_field",
                        "rule_id": "isin-format",
                        "columns": ["isin"],
                        "predicate": "isin-is-valid",
                        "description": "ISIN must be a valid identifier",
                    },
                ],
            },
            {
                "backend": "sample",
                "table": "legacy_params",
                # Deliberately lapsed review window so the seeded
                # changeset demonstrates EXPIRED (D21).
                "review_ttl": -3600,
                "rules": [],
            },
        ],
        "grants": [
            {"principal": "alice", "role": "maker", "scope": "sample/*/*"},
            {"principal": "bob", "role": "checker", "scope": "sample/*/*"},
            {"principal": "carol", "role": "maker", "scope": "sample/*/*"},
            {"principal": "carol", "role": "checker", "scope": "sample/*/*"},
            {"principal": "dave", "role": "reader", "scope": "sample/*/*"},
        ],
    }


def populate(ctx: SeedContext) -> None:
    """Eight changesets, one per lifecycle state reachable without apply."""
    fx = ctx.ref("sample", "fx_rates")
    limits = ctx.ref("sample", "trading_limits")
    holidays = ctx.ref("sample", "holidays")
    legacy = ctx.ref("sample", "legacy_params")
    service = ctx.workflow
    comments = ctx.comments

    def insert(pair: str, rate: float) -> ChangeItem:
        return ChangeItem(op=ChangeOp.INSERT, values={"pair": pair, "rate": rate})

    # DRAFT
    service.create(
        fx,
        maker="alice",
        title="Update GBPUSD rate",
        description="Still collecting desk sign-off before submitting.",
        items=[
            ChangeItem(
                op=ChangeOp.UPDATE, key={"pair": "GBPUSD"}, values={"rate": 1.28}
            )
        ],
    )

    # SUBMITTED (with a comment thread)
    pending = service.create(
        fx,
        maker="alice",
        title="Add JPY rate",
        description="New pair requested by the APAC desk.",
        items=[insert("USDJPY", 155.2)],
    )
    service.submit(pending.id, "alice")
    question = comments.add_comment(
        pending.id, "bob", "Is 155.2 the London or Tokyo close?"
    )
    comments.add_comment(
        pending.id, "alice", "Tokyo close, per desk convention.", parent_id=question.id
    )

    # APPROVED
    approved = service.create(
        fx, maker="alice", title="Add SGD rate", items=[insert("USDSGD", 1.34)]
    )
    service.submit(approved.id, "alice")
    service.approve(approved.id, "bob", reason="Matches vendor feed")

    # REJECTED — a *valid* change the checker declines on business grounds.
    # Since validation runs at submit (D12), an invalid changeset (say a
    # negative rate) never reaches a checker at all: rejection is human
    # judgement, not a stand-in for validation.
    rejected = service.create(
        fx,
        maker="carol",
        title="Add CAD rate",
        description="Requested by the Toronto desk.",
        items=[insert("USDCAD", 1.36)],
    )
    service.submit(rejected.id, "carol")
    service.reject(
        rejected.id, "bob", reason="CAD coverage is not signed off for this quarter yet"
    )

    # WITHDRAWN
    withdrawn = service.create(
        fx, maker="alice", title="Experimental rates", items=[insert("EURGBP", 0.85)]
    )
    service.withdraw(withdrawn.id, "alice")

    # EXPIRED (legacy_params has a lapsed review window)
    stale = service.create(
        legacy,
        maker="alice",
        title="Disable legacy mode permanently",
        items=[
            ChangeItem(
                op=ChangeOp.UPDATE,
                key={"param": "legacy_mode"},
                values={"value": "removed"},
            )
        ],
    )
    service.submit(stale.id, "alice")
    service.expire_overdue()

    # SUBMITTED batch (multi-item update on trading_limits)
    batch = service.create(
        limits,
        maker="alice",
        title="Quarterly limit rebalance",
        description="Risk committee outcome 2026-Q3: raise FX and RATES, trim CREDIT.",
        items=[
            ChangeItem(
                op=ChangeOp.UPDATE, key={"desk": "FX"}, values={"limit": 2_500_000}
            ),
            ChangeItem(
                op=ChangeOp.UPDATE, key={"desk": "RATES"}, values={"limit": 5_500_000}
            ),
            ChangeItem(
                op=ChangeOp.UPDATE, key={"desk": "CREDIT"}, values={"limit": 800_000}
            ),
            ChangeItem(
                op=ChangeOp.INSERT,
                values={"desk": "MACRO", "limit": 1_250_000, "currency": "USD"},
            ),
        ],
    )
    service.submit(batch.id, "alice")
    comments.add_comment(
        batch.id, "bob", "MACRO is a new desk — do we have the risk committee minutes?"
    )

    # APPROVED with SELF-APPROVED badge (holidays allows it, D26/D27)
    solo = service.create(
        holidays,
        maker="carol",
        title="Add New Year 2027",
        description="Routine calendar roll — holidays table permits self-approval.",
        items=[
            ChangeItem(
                op=ChangeOp.INSERT,
                values={"day": "2027-01-01", "name": "New Year's Day", "market": "ALL"},
            )
        ],
    )
    service.submit(solo.id, "carol")
    service.approve(solo.id, "carol")

    ctx.note(
        "5 tables (incl. a 1,200-row instruments table) and eight changesets "
        "incl. a multi-item batch and a self-approved one"
    )
    ctx.note("makers alice & carol, checker bob, reader dave")
