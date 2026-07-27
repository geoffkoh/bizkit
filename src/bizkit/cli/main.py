"""The ``bizkit`` command-line interface.

Identity arrives via ``--user`` / ``BIZKIT_USER`` (spec D6); the
workspace config file via ``--config`` / ``BIZKIT_CONFIG`` (D22).
Commands for later milestones are present as explicit stubs.
"""

import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import click
import uvicorn

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from bizkit.backends.base import BaseBackend
from bizkit.backends.registry import get_backend_class
from bizkit.config import BizkitConfig, load_config
from bizkit.demo import DEFAULT_SCENARIO, SCENARIOS, get_scenario, seed
from bizkit.domain.access import Grant
from bizkit.domain.table import TableRef
from bizkit.domain.validation import ValidationReport
from bizkit.exceptions import BizkitError, StoreSchemaError
from bizkit.services.workflow import WorkflowService
from bizkit.store import schema as store_schema
from bizkit.store.engine import (
    create_session_factory,
    create_store_engine,
)
from bizkit.store.repositories import (
    SqlAlchemyAuditLog,
    SqlAlchemyChangesetRepository,
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
        # AccessDenied or "no target profile". Exempt: `init-store`, whose
        # `--seed-sample` *writes* the file at this path, and the `store`
        # group (D46) — schema plumbing must run before a workspace exists,
        # and must not be blocked by one a pending upgrade would fix.
        if not exists and ctx.invoked_subcommand not in {"init-store", "store"}:
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


def _open_store(url: str) -> Engine:
    """Open the store and refuse to use one whose schema is not at head.

    Commands never migrate implicitly (spec D46) — an upgrade is an operator
    decision, so a mismatch stops the command with the fix in the message.

    Args:
        url: Store URL.

    Returns:
        An engine bound to a store at the expected revision.

    Raises:
        click.ClickException: If the schema is missing, behind, or ahead.
    """
    engine = create_store_engine(url)
    try:
        store_schema.verify_revision(engine)
    except StoreSchemaError as exc:
        raise click.ClickException(str(exc)) from exc
    return engine


@cli.command("init-store")
@click.option(
    "--seed-sample",
    is_flag=True,
    help=f"Seed the {DEFAULT_SCENARIO!r} demo scenario (alias for --scenario).",
)
@click.option(
    "--scenario",
    type=click.Choice(sorted(SCENARIOS)),
    default=None,
    help="Seed a named demo scenario; see --list-scenarios.",
)
@click.option(
    "--list-scenarios",
    is_flag=True,
    help="List the available demo scenarios and exit.",
)
@click.pass_obj
def init_store(
    obj: CLIContext,
    seed_sample: bool,
    scenario: str | None,
    list_scenarios: bool,
) -> None:
    """Create the workflow store by migrating it to head (spec D46).

    Creating a fresh store and upgrading an existing one are the same
    operation, so this is `store upgrade` against an empty database.

    Optionally seed a demo scenario. The scenarios themselves live in
    `bizkit.demo` (spec D45) — this command only resolves the name, picks
    the paths, and reports what was written.
    """
    if list_scenarios:
        for name, defined in sorted(SCENARIOS.items()):
            marker = " (default)" if name == DEFAULT_SCENARIO else ""
            click.echo(f"{name}{marker}\n    {defined.summary}")
        return

    engine = create_store_engine(obj.config.store_url)
    store_schema.upgrade(engine)
    click.echo(
        f"Store initialized at {obj.config.store_url} "
        f"(revision {store_schema.head_revision()})"
    )

    chosen = scenario or (DEFAULT_SCENARIO if seed_sample else None)
    if chosen is None:
        return

    workspace_path = Path(obj.config_path or "bizkit.workspace.json")
    with _domain_errors():
        result = seed(
            get_scenario(chosen),
            store_url=obj.config.store_url,
            workspace_path=workspace_path,
        )
    targets = ", ".join(str(path) for path in result.target_paths.values())
    click.echo(
        f"Seeded {result.scenario!r} — workspace {result.workspace_path}, "
        f"target(s) {targets}"
    )
    for note in result.notes:
        click.echo(f"  {note}")


@cli.group("store")
def store_group() -> None:
    """Workflow store schema management (spec D46)."""


@store_group.command("upgrade")
@click.option(
    "--sql",
    "as_sql",
    is_flag=True,
    help="Emit the DDL instead of running it, for a DBA to apply.",
)
@click.option(
    "--revision",
    default="head",
    show_default=True,
    help="Target revision (or 'from:to' range with --sql).",
)
@click.pass_obj
def store_upgrade(obj: CLIContext, as_sql: bool, revision: str) -> None:
    """Apply pending migrations to the workflow store."""
    if as_sql:
        store_schema.emit_sql(obj.config.store_url, revision)
        return
    engine = create_store_engine(obj.config.store_url)
    before = store_schema.current_revision(engine)
    store_schema.upgrade(engine, revision)
    after = store_schema.current_revision(engine)
    if before == after:
        click.echo(f"Already at revision {after}; nothing to do.")
    else:
        click.echo(f"Upgraded store {before or '(empty)'} -> {after}.")


@store_group.command("current")
@click.pass_obj
def store_current(obj: CLIContext) -> None:
    """Show the store's schema revision and whether it is at head."""
    engine = create_store_engine(obj.config.store_url)
    state = store_schema.describe(engine)
    click.echo(f"current: {state['current'] or '(no schema)'}")
    click.echo(f"head:    {state['head']}")
    click.echo(f"status:  {'up to date' if state['up_to_date'] else 'UPGRADE NEEDED'}")


@store_group.command("history")
def store_history() -> None:
    """List the migration chain, oldest first."""
    for revision, description in store_schema.history():
        click.echo(f"{revision}  {description}")


@store_group.command("stamp")
@click.argument("revision")
@click.pass_obj
def store_stamp(obj: CLIContext, revision: str) -> None:
    """Record REVISION as applied without running it.

    For a store upgraded out of band from `store upgrade --sql` output.
    """
    engine = create_store_engine(obj.config.store_url)
    store_schema.stamp(engine, revision)
    click.echo(f"Stamped store at revision {revision}.")


@cli.command("list")
@click.pass_obj
def list_changesets(obj: CLIContext) -> None:
    """List changesets in the workflow store."""
    engine = _open_store(obj.config.store_url)
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
    engine = _open_store(obj.config.store_url)
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
    engine = _open_store(obj.config.store_url)
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
    engine = _open_store(obj.config.store_url)
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
