"""The ``bizkit`` command-line interface.

Identity arrives via ``--user`` / ``BIZKIT_USER`` (spec D6); the
workspace config file via ``--config`` / ``BIZKIT_CONFIG`` (D22).
Commands for later milestones are present as explicit stubs.
"""

import json
import os
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import click
import uvicorn

from sqlalchemy.orm import Session

from bizkit.backends.base import BaseBackend
from bizkit.backends.registry import get_backend_class
from bizkit.config import BizkitConfig, load_config
from bizkit.domain.access import Grant
from bizkit.domain.changeset import ChangeItem, ChangeOp
from bizkit.domain.table import TableRef
from bizkit.domain.validation import ValidationReport
from bizkit.exceptions import BizkitError
from bizkit.services.comments import CommentService
from bizkit.services.workflow import WorkflowService
from bizkit.store.engine import (
    create_schema,
    create_session_factory,
    create_store_engine,
)
from bizkit.store.repositories import (
    SqlAlchemyAuditLog,
    SqlAlchemyChangesetRepository,
    SqlAlchemyCommentRepository,
    SqlAlchemyDecisionRepository,
)
from bizkit.workspace.access import FileAccessPolicy
from bizkit.workspace.loader import (
    LoadedWorkspace,
    WorkspaceFile,
    check_no_literal_secrets,
    load_workspace,
)
from bizkit.workspace.registry import FileTableRegistry


@dataclass
class CLIContext:
    """Injected per-invocation context (no globals)."""

    config: BizkitConfig
    workspace: LoadedWorkspace | None
    config_path: str | None
    user: str


@click.group()
@click.option(
    "--store-url",
    envvar="BIZKIT_STORE_URL",
    default=None,
    help="Workflow store URL (ignored when --config is given).",
)
@click.option(
    "--config",
    "config_path",
    envvar="BIZKIT_CONFIG",
    type=click.Path(dir_okay=False),
    default=None,
    help="Workspace config file (YAML/JSON, spec D22).",
)
@click.option(
    "--user",
    envvar="BIZKIT_USER",
    default=lambda: os.environ.get("USER", "anonymous"),
    help="Acting identity (authentication is external, spec D6).",
)
@click.pass_context
def cli(
    ctx: click.Context,
    store_url: str | None,
    config_path: str | None,
    user: str,
) -> None:
    """bizkit — maker-checker workflows for configuration tables."""
    workspace: LoadedWorkspace | None = None
    if config_path is not None:
        exists = Path(config_path).exists()
        # Never silently fall back: without the workspace there are no grants
        # and no targets, so the real symptom surfaces much later as a baffling
        # AccessDenied or "no target profile". `init-store` is the one
        # exemption — `--seed-sample` *writes* the file at this path.
        if not exists and ctx.invoked_subcommand != "init-store":
            raise click.ClickException(
                f"Workspace config {config_path!r} does not exist. Pass a path "
                "to an existing YAML/JSON workspace file, or omit --config to "
                "run without one (no grants, no targets)."
            )
        if exists:
            try:
                workspace = load_workspace(config_path)
            except BizkitError as exc:
                raise click.ClickException(str(exc)) from exc
    config = workspace.config if workspace else load_config(store_url)
    ctx.obj = CLIContext(
        config=config, workspace=workspace, config_path=config_path, user=user
    )


@cli.command("init-store")
@click.option(
    "--seed-sample",
    is_flag=True,
    help="Also create a sample workspace, target DB, and pending changeset.",
)
@click.pass_obj
def init_store(obj: CLIContext, seed_sample: bool) -> None:
    """Create the workflow store schema (dev path; see spec D34)."""
    engine = create_store_engine(obj.config.store_url)
    create_schema(engine)
    click.echo(f"Store initialized at {obj.config.store_url}")
    if seed_sample:
        _seed_sample(obj, engine_url=obj.config.store_url)


def _seed_sample(obj: CLIContext, engine_url: str) -> None:
    """Write a sample workspace + target DB + one pending changeset."""
    target_db = Path("sample_target.db")
    with sqlite3.connect(target_db) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS fx_rates "
            "(pair TEXT PRIMARY KEY, rate REAL NOT NULL, "
            "source TEXT NOT NULL DEFAULT 'vendor')"
        )
        # Deliberately omits the pairs the seeded changesets insert (USDJPY,
        # USDSGD, USDCAD, EURGBP): a pending insert has to be for a row that
        # does not exist yet, or applying it trips the primary key. Updates
        # below (GBPUSD) do need their row present.
        conn.executemany(
            "INSERT OR REPLACE INTO fx_rates (pair, rate, source) VALUES (?, ?, ?)",
            [
                ("EURUSD", 1.09, "vendor"),
                ("GBPUSD", 1.27, "vendor"),
                ("AUDUSD", 0.66, "vendor"),
                ("USDCHF", 0.88, "desk"),
                ("NZDUSD", 0.61, "vendor"),
                ("EURCHF", 0.96, "desk"),
                ("USDHKD", 7.81, "vendor"),
                ("USDCNH", 7.24, "vendor"),
            ],
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS trading_limits "
            '(desk TEXT PRIMARY KEY, "limit" REAL NOT NULL, '
            "currency TEXT NOT NULL DEFAULT 'USD')"
        )
        conn.executemany(
            'INSERT OR REPLACE INTO trading_limits (desk, "limit", currency) '
            "VALUES (?, ?, ?)",
            [
                ("FX", 2_000_000, "USD"),
                ("RATES", 5_000_000, "USD"),
                ("CREDIT", 1_000_000, "USD"),
                ("EQUITY", 3_000_000, "USD"),
                ("COMMODITIES", 1_500_000, "EUR"),
                ("EM", 750_000, "SGD"),
            ],
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS holidays "
            "(day TEXT PRIMARY KEY, name TEXT NOT NULL, market TEXT NOT NULL)"
        )
        conn.executemany(
            "INSERT OR REPLACE INTO holidays (day, name, market) VALUES (?, ?, ?)",
            [
                ("2026-12-25", "Christmas Day", "ALL"),
                ("2026-08-09", "National Day", "SG"),
                ("2026-07-04", "Independence Day", "US"),
                ("2026-01-01", "New Year's Day", "ALL"),
                ("2026-05-25", "Memorial Day", "US"),
                ("2026-12-26", "Boxing Day", "UK"),
                ("2026-02-17", "Chinese New Year", "SG"),
                ("2026-11-23", "Labour Thanksgiving", "JP"),
            ],
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS instruments "
            "(isin TEXT PRIMARY KEY, name TEXT NOT NULL, "
            "currency TEXT NOT NULL, asset_class TEXT NOT NULL, "
            "active INTEGER NOT NULL DEFAULT 1)"
        )
        issuers = [
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
        kinds = ["Bond", "Note", "Bill", "Perp", "FRN", "Linker"]
        currencies = ["USD", "EUR", "SGD", "JPY", "GBP", "CHF"]
        classes = ["BOND", "EQUITY", "FX", "COMMODITY"]
        conn.executemany(
            "INSERT OR REPLACE INTO instruments "
            "(isin, name, currency, asset_class, active) VALUES (?, ?, ?, ?, ?)",
            [
                (
                    f"XS{i:010d}",
                    f"{issuers[i % len(issuers)]} "
                    f"{kinds[i % len(kinds)]} {2026 + i % 10}",
                    currencies[i % len(currencies)],
                    classes[i % len(classes)],
                    0 if i % 17 == 0 else 1,
                )
                for i in range(1, 1201)
            ],
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS legacy_params "
            "(param TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.executemany(
            "INSERT OR REPLACE INTO legacy_params (param, value) VALUES (?, ?)",
            [
                ("legacy_mode", "off"),
                ("retry_count", "3"),
                ("eod_cutoff", "17:30"),
            ],
        )
        conn.commit()

    workspace_data = {
        "version": 1,
        "store_url": engine_url,
        "targets": {"sample": {"backend": "sqlite", "url": f"sqlite:///{target_db}"}},
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
                        "allowed_values": [
                            "BOND",
                            "EQUITY",
                            "FX",
                            "COMMODITY",
                        ],
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
    workspace_path = Path(obj.config_path or "bizkit.workspace.json")
    workspace_path.write_text(json.dumps(workspace_data, indent=2), encoding="utf-8")
    loaded = load_workspace(workspace_path)

    engine = create_store_engine(engine_url)
    create_schema(engine)
    factory = create_session_factory(engine)
    fx = TableRef(backend="sample", table="fx_rates")
    limits = TableRef(backend="sample", table="trading_limits")
    holidays = TableRef(backend="sample", table="holidays")
    legacy = TableRef(backend="sample", table="legacy_params")
    with factory() as session:
        changesets = SqlAlchemyChangesetRepository(session)
        audit = SqlAlchemyAuditLog(session)
        service = WorkflowService(
            changesets=changesets,
            audit=audit,
            access=FileAccessPolicy(loaded.grants),
            config=loaded.config.workflow,
            registry=FileTableRegistry(loaded.tables),
            decisions=SqlAlchemyDecisionRepository(session),
        )
        comment_service = CommentService(
            comments=SqlAlchemyCommentRepository(session),
            changesets=changesets,
            audit=audit,
            access=FileAccessPolicy(loaded.grants),
        )

        def _insert(pair: str, rate: float) -> ChangeItem:
            return ChangeItem(op=ChangeOp.INSERT, values={"pair": pair, "rate": rate})

        # DRAFT
        service.create(
            fx,
            maker="alice",
            title="Update GBPUSD rate",
            description="Still collecting desk sign-off before submitting.",
            items=[
                ChangeItem(
                    op=ChangeOp.UPDATE,
                    key={"pair": "GBPUSD"},
                    values={"rate": 1.28},
                )
            ],
        )

        # SUBMITTED (with a comment thread)
        pending = service.create(
            fx,
            maker="alice",
            title="Add JPY rate",
            description="New pair requested by the APAC desk.",
            items=[_insert("USDJPY", 155.2)],
        )
        service.submit(pending.id, "alice")
        question = comment_service.add_comment(
            pending.id, "bob", "Is 155.2 the London or Tokyo close?"
        )
        comment_service.add_comment(
            pending.id,
            "alice",
            "Tokyo close, per desk convention.",
            parent_id=question.id,
        )

        # APPROVED
        approved = service.create(
            fx,
            maker="alice",
            title="Add SGD rate",
            items=[_insert("USDSGD", 1.34)],
        )
        service.submit(approved.id, "alice")
        service.approve(approved.id, "bob", reason="Matches vendor feed")

        # REJECTED — a *valid* change the checker declines on business
        # grounds. Since validation runs at submit (D12), an invalid
        # changeset (say a negative rate) never reaches a checker at all:
        # rejection is human judgement, not a stand-in for validation.
        rejected = service.create(
            fx,
            maker="carol",
            title="Add CAD rate",
            description="Requested by the Toronto desk.",
            items=[_insert("USDCAD", 1.36)],
        )
        service.submit(rejected.id, "carol")
        service.reject(
            rejected.id,
            "bob",
            reason="CAD coverage is not signed off for this quarter yet",
        )

        # WITHDRAWN
        withdrawn = service.create(
            fx,
            maker="alice",
            title="Experimental rates",
            items=[_insert("EURGBP", 0.85)],
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
            description="Risk committee outcome 2026-Q3: raise FX and "
            "RATES, trim CREDIT.",
            items=[
                ChangeItem(
                    op=ChangeOp.UPDATE,
                    key={"desk": "FX"},
                    values={"limit": 2_500_000},
                ),
                ChangeItem(
                    op=ChangeOp.UPDATE,
                    key={"desk": "RATES"},
                    values={"limit": 5_500_000},
                ),
                ChangeItem(
                    op=ChangeOp.UPDATE,
                    key={"desk": "CREDIT"},
                    values={"limit": 800_000},
                ),
                ChangeItem(
                    op=ChangeOp.INSERT,
                    values={
                        "desk": "MACRO",
                        "limit": 1_250_000,
                        "currency": "USD",
                    },
                ),
            ],
        )
        service.submit(batch.id, "alice")
        comment_service.add_comment(
            batch.id,
            "bob",
            "MACRO is a new desk — do we have the risk committee minutes?",
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
                    values={
                        "day": "2027-01-01",
                        "name": "New Year's Day",
                        "market": "ALL",
                    },
                )
            ],
        )
        service.submit(solo.id, "carol")
        service.approve(solo.id, "carol")

        session.commit()
    click.echo(
        f"Seeded workspace {workspace_path}, target {target_db} (5 tables, "
        "incl. a 1,200-row instruments table), "
        "and eight changesets incl. a multi-item batch and a self-approved "
        "one — makers alice & carol, checker bob, reader dave"
    )


@cli.command("list")
@click.pass_obj
def list_changesets(obj: CLIContext) -> None:
    """List changesets in the workflow store."""
    engine = create_store_engine(obj.config.store_url)
    create_schema(engine)
    factory = create_session_factory(engine)
    with factory() as session:
        repo = SqlAlchemyChangesetRepository(session)
        changesets = repo.list()
    if not changesets:
        click.echo("No changesets")
        return
    for cs in changesets:
        click.echo(
            f"{cs.id}  [{cs.state.value:>9}] rev {cs.revision}  "
            f"{cs.table.qualified_name()}  {cs.title!r}  maker={cs.maker}"
        )


@cli.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8091, show_default=True, type=int)
@click.option("--reload", "use_reload", is_flag=True, help="Dev auto-reload.")
@click.pass_obj
def serve(obj: CLIContext, host: str, port: int, use_reload: bool) -> None:
    """Run the API server (serves the SPA when a bundle is present)."""
    if obj.config_path:
        os.environ["BIZKIT_CONFIG"] = obj.config_path
    else:
        os.environ["BIZKIT_STORE_URL"] = obj.config.store_url
    uvicorn.run(
        "bizkit.api.app:app_factory",
        factory=True,
        host=host,
        port=port,
        reload=use_reload,
    )


@cli.command()
@click.pass_obj
def expire(obj: CLIContext) -> None:
    """Sweep overdue changesets into EXPIRED (spec D21)."""
    engine = create_store_engine(obj.config.store_url)
    create_schema(engine)
    factory = create_session_factory(engine)
    registry = FileTableRegistry(obj.workspace.tables) if obj.workspace else None
    grants: list[Grant] = obj.workspace.grants if obj.workspace else []
    with factory() as session:
        service = WorkflowService(
            changesets=SqlAlchemyChangesetRepository(session),
            audit=SqlAlchemyAuditLog(session),
            access=FileAccessPolicy(grants),
            config=obj.config.workflow,
            registry=registry,
        )
        expired = service.expire_overdue()
        session.commit()
    click.echo(f"Expired {len(expired)} changeset(s)")


def _backend_resolver(obj: CLIContext) -> Callable[[TableRef], BaseBackend]:
    """Resolve a table to its configured target backend."""
    targets = obj.config.targets

    def backend_for(ref: TableRef) -> BaseBackend:
        target = targets.get(ref.backend)
        if target is None:
            raise click.ClickException(
                f"No target profile {ref.backend!r} in configuration — "
                "apply needs a target to write to"
            )
        return get_backend_class(target.backend)(target.url)

    return backend_for


def _workflow_service(obj: CLIContext, session: Session) -> WorkflowService:
    """Build a fully-wired WorkflowService over an open session."""
    registry = FileTableRegistry(obj.workspace.tables) if obj.workspace else None
    grants: list[Grant] = obj.workspace.grants if obj.workspace else []
    backend_for = _backend_resolver(obj)

    return WorkflowService(
        changesets=SqlAlchemyChangesetRepository(session),
        audit=SqlAlchemyAuditLog(session),
        access=FileAccessPolicy(grants),
        config=obj.config.workflow,
        registry=registry,
        decisions=SqlAlchemyDecisionRepository(session),
        backend_for=backend_for,
    )


def _echo_issues(report: ValidationReport) -> None:
    for issue in report.issues:
        location = f" [{issue.column}]" if issue.column else ""
        key = f" key={issue.row_key}" if issue.row_key else ""
        click.echo(
            f"  {issue.severity.value}: {issue.rule_id}{location}{key} — "
            f"{issue.message}"
        )


@contextmanager
def _domain_errors() -> Iterator[None]:
    """Surface domain errors as clean CLI messages, not tracebacks."""
    try:
        yield
    except BizkitError as exc:
        raise click.ClickException(str(exc)) from exc


@cli.command()
@click.argument("changeset_id")
@click.option("--actor", required=True, help="Principal applying the changeset.")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Rehearse against the target and roll back; changes no state.",
)
@click.pass_obj
def apply(obj: CLIContext, changeset_id: str, actor: str, dry_run: bool) -> None:
    """Apply an APPROVED changeset to its target database (spec §5).

    Revalidates first (D12) because the target may have drifted since
    approval, then hands the write to the backend. On failure the changeset
    lands in FAILED and can be reworked or retried.
    """
    engine = create_store_engine(obj.config.store_url)
    create_schema(engine)
    factory = create_session_factory(engine)
    with factory() as session, _domain_errors():
        service = _workflow_service(obj, session)
        if dry_run:
            changeset = SqlAlchemyChangesetRepository(session).get(changeset_id)
            report = service.validate(changeset)
            if not report.ok:
                click.echo("Validation failed:")
                _echo_issues(report)
                raise SystemExit(1)
            _backend_resolver(obj)(changeset.table).dry_run(changeset)
            click.echo(
                f"Dry run OK — {len(changeset.items)} item(s) rehearsed against "
                f"{changeset.table.qualified_name()}, target unchanged"
            )
            return

        result = service.apply(changeset_id, actor)
        session.commit()

    if result.ok:
        click.echo(
            f"Applied {changeset_id} to {result.changeset.table.qualified_name()} "
            f"({len(result.changeset.items)} item(s))"
        )
        return
    click.echo(f"Apply failed — changeset is now {result.changeset.state.value}")
    if result.report is not None:
        _echo_issues(result.report)
    if result.error:
        click.echo(f"  target: {result.error}")
    raise SystemExit(1)


@cli.command()
@click.argument("changeset_id")
@click.pass_obj
def validate(obj: CLIContext, changeset_id: str) -> None:
    """Run a changeset's rule set and report, changing nothing (D12)."""
    engine = create_store_engine(obj.config.store_url)
    create_schema(engine)
    factory = create_session_factory(engine)
    with factory() as session, _domain_errors():
        service = _workflow_service(obj, session)
        changeset = SqlAlchemyChangesetRepository(session).get(changeset_id)
        report = service.validate(changeset)
    if report.ok:
        click.echo(f"OK — no blocking issues in {len(changeset.items)} item(s)")
        return
    click.echo(f"{len(report.issues)} issue(s):")
    _echo_issues(report)
    raise SystemExit(1)


@cli.group("config")
def config_group() -> None:
    """Workspace config tooling (spec D23)."""


@config_group.command("validate")
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
def config_validate(path: str) -> None:
    """Lint a workspace file; print fingerprint and effective posture."""
    raw_text = Path(path).read_text(encoding="utf-8-sig")
    secrets = check_no_literal_secrets(raw_text)
    if secrets:
        raise click.ClickException(
            "Literal credentials found in URLs "
            f"({', '.join(secrets)}); use ${{ENV_VAR}} indirection (spec D30)"
        )
    try:
        loaded = load_workspace(path)
    except BizkitError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"OK  fingerprint sha256:{loaded.fingerprint[:16]}…")
    global_flag = loaded.config.workflow.allow_self_approval
    click.echo(f"Global allow_self_approval: {global_flag}")
    for table in loaded.tables:
        effective = (
            table.allow_self_approval
            if table.allow_self_approval is not None
            else global_flag
        )
        marker = "  SELF-APPROVAL LIVE" if effective else ""
        click.echo(
            f"  {table.table.backend}/"
            f"{table.table.schema_name or '*'}/{table.table.table}: "
            f"self-approval={effective}{marker}"
        )


@config_group.command("schema")
def config_schema() -> None:
    """Emit the workspace file JSON Schema (spec D23)."""
    click.echo(json.dumps(WorkspaceFile.model_json_schema(), indent=2))


def _not_implemented(name: str) -> click.Command:
    @cli.command(
        name,
        help=f"({name}) Not implemented yet — see SPECIFICATION.md §13.",
    )
    def _stub() -> None:
        raise click.ClickException(
            f"'{name}' is not implemented yet — see SPECIFICATION.md §13"
        )

    return _stub


for _name in ("show", "submit", "review", "comment"):
    _not_implemented(_name)


if __name__ == "__main__":
    cli()
