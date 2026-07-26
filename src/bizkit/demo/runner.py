"""Executes a demo scenario: target databases, workspace file, workflow history."""

import json
import sqlite3
from pathlib import Path

from bizkit.backends.base import BaseBackend
from bizkit.backends.registry import get_backend_class
from bizkit.demo.model import Scenario, SeedContext, SeedResult, TargetTable
from bizkit.domain.table import TableRef
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
from bizkit.workspace.loader import load_workspace
from bizkit.workspace.registry import FileTableRegistry


def _build_target(
    path: Path, tables: list[TargetTable] | tuple[TargetTable, ...]
) -> None:
    """Create and populate one demo target database.

    Uses raw `sqlite3` rather than a backend: this is *setup* of a target
    that bizkit will later govern, not a bizkit-mediated change. Governed
    writes only ever happen through `BaseBackend.apply()`.
    """
    with sqlite3.connect(path) as conn:
        for table in tables:
            conn.execute(table.ddl)
            if not table.rows:
                continue
            columns = ", ".join(f'"{c}"' for c in table.columns)
            placeholders = ", ".join("?" for _ in table.columns)
            conn.executemany(
                f'INSERT OR REPLACE INTO "{table.name}" ({columns}) '  # noqa: S608
                f"VALUES ({placeholders})",
                [tuple(row) for row in table.rows],
            )
        conn.commit()


def seed(
    scenario: Scenario,
    store_url: str,
    workspace_path: Path,
    directory: Path | None = None,
) -> SeedResult:
    """Run a scenario end to end.

    Args:
        scenario: The scenario to seed.
        store_url: Workflow store URL; written into the workspace config.
        workspace_path: Where to write the workspace config file.
        directory: Where target database files go; defaults to the
            workspace file's directory.

    Returns:
        A :class:`SeedResult` describing what was written.
    """
    base = directory if directory is not None else (workspace_path.parent or Path())
    target_paths = {
        profile: base / f"{profile}_target.db" for profile in scenario.targets
    }
    for profile, tables in scenario.targets.items():
        _build_target(target_paths[profile], list(tables))

    workspace_data = scenario.workspace(store_url, target_paths)
    workspace_path.write_text(json.dumps(workspace_data, indent=2), encoding="utf-8")
    loaded = load_workspace(workspace_path)

    engine = create_store_engine(store_url)
    create_schema(engine)
    factory = create_session_factory(engine)

    backend_cache: dict[str, BaseBackend] = {}

    def backend_for(ref: TableRef) -> BaseBackend:
        target = loaded.config.targets[ref.backend]
        if ref.backend not in backend_cache:
            backend_cache[ref.backend] = get_backend_class(target.backend)(target.url)
        return backend_cache[ref.backend]

    access = FileAccessPolicy(loaded.grants)
    refs = {
        (config.table.backend, config.table.table): config.table
        for config in loaded.tables
    }

    with factory() as session:
        changesets = SqlAlchemyChangesetRepository(session)
        audit = SqlAlchemyAuditLog(session)
        context = SeedContext(
            workflow=WorkflowService(
                changesets=changesets,
                audit=audit,
                access=access,
                config=loaded.config.workflow,
                registry=FileTableRegistry(loaded.tables),
                decisions=SqlAlchemyDecisionRepository(session),
                backend_for=backend_for,
            ),
            comments=CommentService(
                comments=SqlAlchemyCommentRepository(session),
                changesets=changesets,
                audit=audit,
                access=access,
            ),
            refs=refs,
        )
        scenario.populate(context)
        session.commit()

    return SeedResult(
        scenario=scenario.name,
        workspace_path=workspace_path,
        target_paths=target_paths,
        notes=list(context.notes),
    )
