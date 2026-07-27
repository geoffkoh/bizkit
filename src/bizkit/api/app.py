"""FastAPI application factory.

Sync (``def``) routes so the sync store runs in the threadpool (spec D2).
Business endpoints live under ``/api/v1`` (D33); health/readiness are
unversioned (D32). Identity arrives via the trusted ``X-Bizkit-User``
header in the dev default (D6) — real deployments put auth middleware in
front. Enforcement always happens server-side in the services; the
affordance fields in responses are UX hints only (D25/D28).
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from bizkit.api.schemas import (
    ApplyResultOut,
    AuditEventOut,
    ChangesetDetailOut,
    ChangesetOut,
    ColumnOut,
    CommentIn,
    CommentOut,
    CreateChangesetIn,
    DecisionOut,
    HealthOut,
    ImportIssueOut,
    ImportReportOut,
    MeOut,
    ReadyOut,
    ReviewIn,
    RowsOut,
    TableOut,
    ValidationReportOut,
)
from bizkit.backends.base import BaseBackend
from bizkit.backends.registry import get_backend_class
from bizkit.config import BizkitConfig, load_config
from bizkit.domain.access import Action
from bizkit.domain.changeset import ChangeItem
from bizkit.domain.table import TableRef
from bizkit.exceptions import (
    AccessDeniedError,
    ApprovalError,
    BizkitError,
    ChangesetLimitError,
    ChangesetStateError,
    ConcurrencyError,
    ConfigError,
    StoreError,
    ValidationFailedError,
)
from bizkit.services.comments import CommentService
from bizkit.services.importer import ImportMode, ImportReport, ImportService
from bizkit.services.workflow import WorkflowService
from bizkit.store.engine import (
    create_session_factory,
    create_store_engine,
)
from bizkit.store.schema import describe, verify_revision
from bizkit.store.repositories import (
    SqlAlchemyAuditLog,
    SqlAlchemyChangesetRepository,
    SqlAlchemyCommentRepository,
    SqlAlchemyDecisionRepository,
)
from bizkit.workspace.access import FileAccessPolicy
from bizkit.workspace.loader import LoadedWorkspace, load_workspace
from bizkit.workspace.registry import FileTableRegistry

_STATIC_DIR = Path(__file__).parent / "static"

_ERROR_STATUS: dict[type[BizkitError], int] = {
    AccessDeniedError: 403,
    ApprovalError: 403,
    ChangesetStateError: 409,
    ConcurrencyError: 409,
    ChangesetLimitError: 422,
    ValidationFailedError: 422,
    StoreError: 404,
    ConfigError: 500,
}


def _identity(x_bizkit_user: str = Header(default="anonymous")) -> str:
    """Dev identity: trusted header (D6); real deployments front with auth."""
    return x_bizkit_user


@dataclass
class _UnitOfWork:
    """Per-request session with services wired over shared repositories."""

    session: Session
    workflow: WorkflowService
    comments: CommentService
    changesets: SqlAlchemyChangesetRepository
    comment_repo: SqlAlchemyCommentRepository
    decisions: SqlAlchemyDecisionRepository
    audit: SqlAlchemyAuditLog


def create_app(
    config: BizkitConfig | None = None,
    workspace: LoadedWorkspace | None = None,
) -> FastAPI:
    """Build the bizkit API application.

    Args:
        config: Injected configuration; defaults to a local SQLite store.
            Ignored when ``workspace`` is provided (its config wins).
        workspace: Loaded workspace file, when running file-first (D22).

    Returns:
        The configured FastAPI app.
    """
    effective = (
        workspace.config if workspace is not None else (config or BizkitConfig())
    )
    engine = create_store_engine(effective.store_url)
    verify_revision(engine)
    session_factory = create_session_factory(engine)

    access_policy = FileAccessPolicy(workspace.grants if workspace else [])
    registry = FileTableRegistry(workspace.tables if workspace else [])
    tables = workspace.tables if workspace else []

    app = FastAPI(title="bizkit", version="0.1.0")
    app.state.config = effective
    app.state.session_factory = session_factory
    app.state.engine = engine
    app.state.fingerprint = workspace.fingerprint if workspace is not None else None

    @app.exception_handler(BizkitError)
    def bizkit_error_handler(request: Request, exc: BizkitError) -> JSONResponse:
        status = _ERROR_STATUS.get(type(exc), 500)
        return JSONResponse(status_code=status, content={"detail": str(exc)})

    @contextmanager
    def unit_of_work() -> Iterator[_UnitOfWork]:
        with session_factory() as session:
            changesets = SqlAlchemyChangesetRepository(session)
            comment_repo = SqlAlchemyCommentRepository(session)
            decisions = SqlAlchemyDecisionRepository(session)
            audit = SqlAlchemyAuditLog(session)
            workflow = WorkflowService(
                changesets=changesets,
                audit=audit,
                access=access_policy,
                config=effective.workflow,
                registry=registry,
                decisions=decisions,
                # Late-bound: `_backend_for_ref` is defined below and only
                # called per-request. Apply and cross-table validation both
                # need it.
                backend_for=lambda ref: _backend_for_ref(ref),
            )
            comments = CommentService(
                comments=comment_repo,
                changesets=changesets,
                audit=audit,
                access=access_policy,
            )
            yield _UnitOfWork(
                session=session,
                workflow=workflow,
                comments=comments,
                changesets=changesets,
                comment_repo=comment_repo,
                decisions=decisions,
                audit=audit,
            )

    # -- unversioned infrastructure (D32) --------------------------------

    @app.get("/api/health", response_model=HealthOut)
    def health() -> HealthOut:
        """Liveness probe."""
        return HealthOut()

    @app.get("/api/ready", response_model=ReadyOut)
    def ready(request: Request) -> ReadyOut:
        """Readiness probe: store reachable, at head revision, config loaded."""
        store_ok = True
        revision: str | None = None
        at_head = False
        try:
            with request.app.state.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            state = describe(request.app.state.engine)
            revision, at_head = state["current"], state["up_to_date"]
        except Exception:  # noqa: BLE001 - readiness must not raise
            store_ok = False
        fingerprint: str | None = request.app.state.fingerprint
        return ReadyOut(
            status="ready" if store_ok and at_head else "degraded",
            store=store_ok,
            store_revision=revision,
            store_up_to_date=at_head,
            config_fingerprint=fingerprint,
        )

    # -- identity and tables ---------------------------------------------

    @app.get("/api/v1/me", response_model=MeOut)
    def me(user: str = Depends(_identity)) -> MeOut:
        """The caller's identity (dev header middleware)."""
        return MeOut(user=user)

    @app.get("/api/v1/tables", response_model=list[TableOut])
    def list_tables(user: str = Depends(_identity)) -> list[TableOut]:
        """Registered configuration tables + the caller's affordances."""
        return [
            TableOut.from_config(
                table_config,
                actor=user,
                policy=access_policy,
                global_self_approval=effective.workflow.allow_self_approval,
                global_max_items=effective.workflow.max_changeset_items,
            )
            for table_config in tables
        ]

    # -- table browsing (D38/D39): read-only target access -----------------

    _backend_cache: dict[str, BaseBackend] = {}

    def _backend_for_ref(ref: TableRef) -> BaseBackend:
        target = effective.targets.get(ref.backend)
        if target is None:
            raise HTTPException(
                status_code=404,
                detail=f"No target profile {ref.backend!r} in configuration",
            )
        if ref.backend not in _backend_cache:
            backend_class = get_backend_class(target.backend)
            _backend_cache[ref.backend] = backend_class(target.url)
        return _backend_cache[ref.backend]

    def _resolve_browse(
        backend: str, schema: str, table: str, user: str
    ) -> tuple[TableRef, BaseBackend]:
        ref = TableRef(
            backend=backend,
            schema_name=None if schema in ("-", "") else schema,
            table=table,
        )
        if registry.lookup(ref) is None:
            raise HTTPException(
                status_code=404,
                detail=f"Table {backend}/{schema}/{table} "
                "is not registered in the workspace config",
            )
        if not access_policy.is_allowed(user, Action.VIEW, ref):
            raise AccessDeniedError(
                f"User {user!r} lacks 'view' rights on {ref.qualified_name()}"
            )
        return ref, _backend_for_ref(ref)

    @app.get(
        "/api/v1/tables/{backend}/{schema}/{table}/columns",
        response_model=list[ColumnOut],
    )
    def table_columns(
        backend: str,
        schema: str,
        table: str,
        user: str = Depends(_identity),
    ) -> list[ColumnOut]:
        """Introspected columns of a registered table (requires view)."""
        ref, target_backend = _resolve_browse(backend, schema, table, user)
        return [
            ColumnOut(
                name=c.name,
                type=c.type,
                nullable=c.nullable,
                primary_key=c.primary_key,
            )
            for c in target_backend.introspect_table(ref)
        ]

    @app.get(
        "/api/v1/tables/{backend}/{schema}/{table}/rows",
        response_model=RowsOut,
    )
    def table_rows(
        backend: str,
        schema: str,
        table: str,
        page: int = 1,
        page_size: int = 50,
        q: str = "",
        sort: str = "",
        direction: str = "asc",
        user: str = Depends(_identity),
    ) -> RowsOut:
        """One page of current rows (read-only via the backend port, D13).

        ``q`` filters across all columns; ``sort``/``direction`` order the
        result. Both run in-process on the API tier — push-down into the
        backend port is the roadmap item for genuinely large tables.
        ``total`` reflects the filtered count so pagination stays honest.
        """
        ref, target_backend = _resolve_browse(backend, schema, table, user)
        columns = [c.name for c in target_backend.introspect_table(ref)]
        all_rows = target_backend.read_rows(ref, columns)

        if q:
            needle = q.lower()
            all_rows = [
                row
                for row in all_rows
                if any(
                    needle in str(value if value is not None else "").lower()
                    for value in row.values()
                )
            ]
        if sort:
            if sort not in columns:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unknown sort column {sort!r}",
                )
            values = [row.get(sort) for row in all_rows]
            numeric = all(
                value is None or isinstance(value, (int, float)) for value in values
            )

            def sort_key(row: dict[str, object]) -> tuple[bool, object]:
                value = row.get(sort)
                if numeric:
                    return (value is None, value if value is not None else 0)
                return (value is None, str(value if value is not None else "").lower())

            all_rows = sorted(all_rows, key=sort_key, reverse=direction == "desc")

        page = max(page, 1)
        page_size = min(max(page_size, 1), 500)
        start = (page - 1) * page_size
        return RowsOut(
            rows=all_rows[start : start + page_size],
            total=len(all_rows),
            page=page,
            page_size=page_size,
        )

    # -- changesets -------------------------------------------------------

    @app.get("/api/v1/changesets", response_model=list[ChangesetOut])
    def list_changesets() -> list[ChangesetOut]:
        """List all changesets."""
        with unit_of_work() as uow:
            return [ChangesetOut.from_domain(cs) for cs in uow.changesets.list()]

    @app.post(
        "/api/v1/changesets",
        response_model=ChangesetDetailOut,
        status_code=201,
    )
    def create_changeset(
        body: CreateChangesetIn, user: str = Depends(_identity)
    ) -> ChangesetDetailOut:
        """Create a draft changeset (maker = caller); optionally submit."""
        ref = TableRef(
            backend=body.backend,
            schema_name=body.schema_name,
            table=body.table,
        )
        with unit_of_work() as uow:
            changeset = uow.workflow.create(
                table=ref,
                maker=user,
                title=body.title,
                description=body.description,
                items=[
                    ChangeItem(op=i.op, key=i.key, values=i.values) for i in body.items
                ],
            )
            if body.submit_now:
                changeset = uow.workflow.submit(changeset.id, user)
            uow.session.commit()
            return ChangesetDetailOut.from_domain(changeset)

    @app.get(
        "/api/v1/changesets/{changeset_id}",
        response_model=ChangesetDetailOut,
    )
    def get_changeset(changeset_id: str) -> ChangesetDetailOut:
        """Fetch one changeset with its items."""
        with unit_of_work() as uow:
            return ChangesetDetailOut.from_domain(uow.changesets.get(changeset_id))

    # -- workflow transitions ---------------------------------------------

    def _transition_route(
        changeset_id: str,
        user: str,
        action: str,
        reason: str = "",
    ) -> ChangesetDetailOut:
        with unit_of_work() as uow:
            if action == "submit":
                changeset = uow.workflow.submit(changeset_id, user)
            elif action == "approve":
                changeset = uow.workflow.approve(changeset_id, user, reason)
            elif action == "reject":
                changeset = uow.workflow.reject(changeset_id, user, reason)
            elif action == "rework":
                changeset = uow.workflow.rework(changeset_id, user)
            else:
                changeset = uow.workflow.withdraw(changeset_id, user)
            uow.session.commit()
            return ChangesetDetailOut.from_domain(changeset)

    @app.post(
        "/api/v1/changesets/{changeset_id}/submit",
        response_model=ChangesetDetailOut,
    )
    def submit_changeset(
        changeset_id: str, user: str = Depends(_identity)
    ) -> ChangesetDetailOut:
        """Submit a draft for review (maker only)."""
        return _transition_route(changeset_id, user, "submit")

    @app.post(
        "/api/v1/changesets/{changeset_id}/approve",
        response_model=ChangesetDetailOut,
    )
    def approve_changeset(
        changeset_id: str,
        body: ReviewIn | None = None,
        user: str = Depends(_identity),
    ) -> ChangesetDetailOut:
        """Approve a submitted changeset (checker; four-eyes enforced)."""
        return _transition_route(
            changeset_id, user, "approve", body.reason if body else ""
        )

    @app.post(
        "/api/v1/changesets/{changeset_id}/reject",
        response_model=ChangesetDetailOut,
    )
    def reject_changeset(
        changeset_id: str,
        body: ReviewIn,
        user: str = Depends(_identity),
    ) -> ChangesetDetailOut:
        """Reject a submitted changeset (checker; reason required)."""
        return _transition_route(changeset_id, user, "reject", body.reason)

    @app.post(
        "/api/v1/changesets/{changeset_id}/rework",
        response_model=ChangesetDetailOut,
    )
    def rework_changeset(
        changeset_id: str, user: str = Depends(_identity)
    ) -> ChangesetDetailOut:
        """Return a rejected/failed/expired changeset to DRAFT (maker)."""
        return _transition_route(changeset_id, user, "rework")

    @app.post(
        "/api/v1/changesets/{changeset_id}/withdraw",
        response_model=ChangesetDetailOut,
    )
    def withdraw_changeset(
        changeset_id: str, user: str = Depends(_identity)
    ) -> ChangesetDetailOut:
        """Withdraw a draft/submitted changeset (maker only)."""
        return _transition_route(changeset_id, user, "withdraw")

    @app.post(
        "/api/v1/changesets/{changeset_id}/apply",
        response_model=ApplyResultOut,
    )
    async def apply_changeset(
        changeset_id: str, user: str = Depends(_identity)
    ) -> ApplyResultOut:
        """Apply an approved changeset to its target database (spec §5).

        The only route that reaches a target, and it only ever delegates to
        `WorkflowService.apply` — which revalidates first (D12) and hands the
        write to `BaseBackend.apply`. Runs in a threadpool because the store
        and target tiers are both sync.
        """

        def _run() -> ApplyResultOut:
            with unit_of_work() as uow:
                result = uow.workflow.apply(changeset_id, user)
                # Commit either way: a FAILED transition and its audit event
                # are as much a part of the record as a successful apply.
                uow.session.commit()
                return ApplyResultOut.from_domain(result)

        return await run_in_threadpool(_run)

    # -- comments, decisions, audit ---------------------------------------

    @app.get(
        "/api/v1/changesets/{changeset_id}/comments",
        response_model=list[CommentOut],
    )
    def list_comments(changeset_id: str) -> list[CommentOut]:
        """A changeset's comments in creation order."""
        with unit_of_work() as uow:
            return [
                CommentOut.from_domain(c) for c in uow.comments.thread_for(changeset_id)
            ]

    @app.post(
        "/api/v1/changesets/{changeset_id}/comments",
        response_model=CommentOut,
        status_code=201,
    )
    def add_comment(
        changeset_id: str,
        body: CommentIn,
        user: str = Depends(_identity),
    ) -> CommentOut:
        """Add a comment or threaded reply."""
        with unit_of_work() as uow:
            comment = uow.comments.add_comment(
                changeset_id, user, body.body, body.parent_id
            )
            uow.session.commit()
            return CommentOut.from_domain(comment)

    @app.get(
        "/api/v1/changesets/{changeset_id}/decisions",
        response_model=list[DecisionOut],
    )
    def list_decisions(changeset_id: str) -> list[DecisionOut]:
        """Review decisions; self-approvals flagged (D26)."""
        with unit_of_work() as uow:
            changeset = uow.changesets.get(changeset_id)
            return [
                DecisionOut.from_domain(d, maker=changeset.maker)
                for d in uow.decisions.list_for(changeset_id)
            ]

    @app.get(
        "/api/v1/changesets/{changeset_id}/audit",
        response_model=list[AuditEventOut],
    )
    def list_audit(changeset_id: str) -> list[AuditEventOut]:
        """The changeset's audit trail in append order."""
        with unit_of_work() as uow:
            return [
                AuditEventOut.from_domain(e) for e in uow.audit.list_for(changeset_id)
            ]

    # -- later milestones --------------------------------------------------

    @app.post(
        "/api/v1/changesets/{changeset_id}/validate",
        response_model=ValidationReportOut,
    )
    async def validate_changeset(
        changeset_id: str, user: str = Depends(_identity)
    ) -> ValidationReportOut:
        """Run the table's rule set without transitioning anything (D12).

        Lets a maker see the report before submitting. Read-only: cross-table
        rules read the target, nothing writes.
        """

        def _run() -> ValidationReportOut:
            with unit_of_work() as uow:
                changeset = uow.changesets.get(changeset_id)
                if not access_policy.is_allowed(user, Action.VIEW, changeset.table):
                    raise AccessDeniedError(
                        f"User {user!r} lacks 'view' rights on "
                        f"{changeset.table.qualified_name()}"
                    )
                return ValidationReportOut.from_domain(uow.workflow.validate(changeset))

        return await run_in_threadpool(_run)

    @app.post(
        "/api/v1/changesets/{changeset_id}/items/import",
        response_model=ImportReportOut,
    )
    async def import_items(
        changeset_id: str,
        request: Request,
        mode: str = "append",
        filename: str = "upload.csv",
        user: str = Depends(_identity),
    ) -> ImportReportOut:
        """Bulk CSV import into a DRAFT changeset (D36).

        Body is raw ``text/csv`` (no multipart, keeping dependencies
        lean); ``mode`` is ``append`` or ``diff``.
        """
        try:
            import_mode = ImportMode(mode)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown mode {mode!r} (expected append or diff)",
            ) from None
        content = await request.body()

        def _run() -> ImportReport:
            with unit_of_work() as uow:
                importer = ImportService(
                    changesets=uow.changesets,
                    audit=uow.audit,
                    access=access_policy,
                    config=effective.workflow,
                    registry=registry,
                    backend_for=_backend_for_ref,
                )
                report = importer.import_csv(
                    changeset_id, user, filename, content, import_mode
                )
                if report.ok:
                    uow.session.commit()
                return report

        report = await run_in_threadpool(_run)
        return ImportReportOut(
            ok=report.ok,
            items_added=report.items_added,
            issues=[
                ImportIssueOut(row=i.row, column=i.column, message=i.message)
                for i in report.issues
            ],
        )

    if (_STATIC_DIR / "index.html").exists():
        app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="spa")

    return app


def app_factory() -> FastAPI:
    """Uvicorn factory entry point (used by ``bizkit serve``).

    Reads ``BIZKIT_CONFIG`` (workspace file path) or ``BIZKIT_STORE_URL``
    from the environment so ``--reload`` workers can rebuild the app.
    """
    config_path = os.environ.get("BIZKIT_CONFIG")
    if config_path:
        return create_app(workspace=load_workspace(config_path))
    return create_app(config=load_config(os.environ.get("BIZKIT_STORE_URL")))
