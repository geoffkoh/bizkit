"""Shared fixtures: in-memory store, repositories, sample domain objects."""

from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from bizkit.domain.access import Grant, Role, Scope
from bizkit.domain.changeset import ChangeItem, ChangeOp, Changeset
from bizkit.domain.table import TableRef
from bizkit.store.engine import (
    create_session_factory,
    create_store_engine,
)
from bizkit.store.repositories import (
    SqlAlchemyAuditLog,
    SqlAlchemyChangesetRepository,
    SqlAlchemyDecisionRepository,
)
from bizkit.store.schema import upgrade
from bizkit.workspace.access import FileAccessPolicy


@pytest.fixture
def migrate_store() -> Callable[[str], None]:
    """Migrate a store URL to head, as a deployment would before starting.

    `create_app` verifies the schema and refuses to migrate on its own
    (spec D46), so anything constructing an app must do this first.

    Returns:
        A callable taking the store URL.
    """

    def _migrate(url: str) -> None:
        engine = create_store_engine(url)
        try:
            upgrade(engine)
        finally:
            engine.dispose()

    return _migrate


@pytest.fixture
def store_engine() -> Iterator[Engine]:
    """In-memory SQLite store migrated to head.

    The fast suite runs the real migration chain rather than a shortcut, so
    every revision is exercised on every run (spec D46).
    """
    engine = create_store_engine("sqlite+pysqlite:///:memory:")
    upgrade(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def store_session(store_engine: Engine) -> Iterator[Session]:
    """A session over the in-memory store."""
    factory = create_session_factory(store_engine)
    with factory() as session:
        yield session


@pytest.fixture
def changeset_repo(store_session: Session) -> SqlAlchemyChangesetRepository:
    """Changeset repository bound to the test session."""
    return SqlAlchemyChangesetRepository(store_session)


@pytest.fixture
def audit_log(store_session: Session) -> SqlAlchemyAuditLog:
    """Audit log bound to the test session."""
    return SqlAlchemyAuditLog(store_session)


@pytest.fixture
def decision_repo(store_session: Session) -> SqlAlchemyDecisionRepository:
    """Decision repository bound to the test session."""
    return SqlAlchemyDecisionRepository(store_session)


@pytest.fixture
def fx_table() -> TableRef:
    """A sample table reference."""
    return TableRef(backend="sample", schema_name=None, table="fx_rates")


@pytest.fixture
def sample_changeset(fx_table: TableRef) -> Changeset:
    """A draft changeset by alice with one insert item."""
    return Changeset(
        table=fx_table,
        maker="alice",
        title="Add EURUSD",
        items=[ChangeItem(op=ChangeOp.INSERT, values={"pair": "EURUSD", "rate": 1.09})],
    )


@pytest.fixture
def maker_checker_policy() -> FileAccessPolicy:
    """alice = maker, bob = checker on everything under 'sample'."""
    return FileAccessPolicy(
        [
            Grant(
                principal="alice",
                role=Role.MAKER,
                scope=Scope.parse("sample/*/*"),
            ),
            Grant(
                principal="bob",
                role=Role.CHECKER,
                scope=Scope.parse("sample/*/*"),
            ),
        ]
    )
