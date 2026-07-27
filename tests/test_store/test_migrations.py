"""Store schema lifecycle: migrations, retention, and drift (spec D45).

The retention test is the one that makes D45's promise checkable: an
upgrade must carry existing changesets, decisions, comments, and audit
events forward untouched. Everything else here guards the surrounding
policy — no implicit migration, no silent start against a mismatched
store, and offline DDL that touches nothing.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from bizkit.api.app import create_app
from bizkit.config import BizkitConfig
from bizkit.domain.approval import Decision, ReviewDecision
from bizkit.domain.audit import AuditEvent
from bizkit.domain.changeset import Changeset
from bizkit.domain.comment import Comment
from bizkit.exceptions import StoreSchemaError
from bizkit.store import schema
from bizkit.store.engine import create_session_factory, create_store_engine
from bizkit.store.repositories import (
    SqlAlchemyAuditLog,
    SqlAlchemyChangesetRepository,
    SqlAlchemyCommentRepository,
    SqlAlchemyDecisionRepository,
)


@pytest.fixture
def store_url(tmp_path: Path) -> str:
    """A file-backed store URL (an upgrade must survive reconnection)."""
    return f"sqlite+pysqlite:///{tmp_path / 'store.db'}"


def test_upgrade_creates_the_schema_from_empty(store_url: str) -> None:
    engine = create_store_engine(store_url)
    assert schema.current_revision(engine) is None

    schema.upgrade(engine)

    assert schema.current_revision(engine) == schema.head_revision()
    tables = set(inspect(engine).get_table_names())
    assert {
        "bizkit_changesets",
        "bizkit_review_decisions",
        "bizkit_comments",
        "bizkit_audit_events",
        "alembic_version",
    } <= tables


def test_upgrade_is_idempotent(store_url: str) -> None:
    engine = create_store_engine(store_url)
    schema.upgrade(engine)
    schema.upgrade(engine)
    assert schema.current_revision(engine) == schema.head_revision()


def test_upgrade_retains_existing_rows(
    store_url: str, sample_changeset: Changeset
) -> None:
    """The D45 guarantee: an upgrade never costs an operator their data.

    Populates every store table at the current head, re-runs the chain, and
    checks each row back — including the audit trail, whose append-only
    ordering (``seq``) must be preserved (D35).
    """
    engine = create_store_engine(store_url)
    schema.upgrade(engine)
    factory = create_session_factory(engine)

    with factory() as session:
        SqlAlchemyChangesetRepository(session).add(sample_changeset)
        SqlAlchemyDecisionRepository(session).add(
            ReviewDecision(
                changeset_id=sample_changeset.id,
                revision=1,
                checker="bob",
                decision=Decision.APPROVE,
                reason="looks right",
            )
        )
        SqlAlchemyCommentRepository(session).add(
            Comment(
                changeset_id=sample_changeset.id,
                author="alice",
                body="ready for review",
            )
        )
        audit = SqlAlchemyAuditLog(session)
        for action in ("create", "submit", "approve"):
            audit.append(
                AuditEvent(
                    changeset_id=sample_changeset.id,
                    actor="alice",
                    action=action,
                )
            )
        session.commit()

    schema.upgrade(engine)

    with factory() as session:
        reloaded = SqlAlchemyChangesetRepository(session).get(sample_changeset.id)
        assert reloaded == sample_changeset

        decisions = SqlAlchemyDecisionRepository(session).list_for(sample_changeset.id)
        assert [d.checker for d in decisions] == ["bob"]
        assert decisions[0].decision is Decision.APPROVE

        comments = SqlAlchemyCommentRepository(session).list_for(sample_changeset.id)
        assert [c.body for c in comments] == ["ready for review"]

        events = SqlAlchemyAuditLog(session).list_for(sample_changeset.id)
        assert [e.action for e in events] == ["create", "submit", "approve"]


def test_baseline_adopts_a_store_created_before_migrations(store_url: str) -> None:
    """A pre-D45 store (created by ``create_all``) upgrades without loss.

    The baseline detects the existing tables and stamps instead of
    recreating them, so the audit trail survives adoption.
    """
    engine = create_store_engine(store_url)
    from bizkit.store.models import Base

    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO bizkit_audit_events "
                "(event_id, changeset_id, payload) VALUES ('e1', 'c1', '{}')"
            )
        )

    schema.upgrade(engine)

    assert schema.current_revision(engine) == schema.head_revision()
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT event_id FROM bizkit_audit_events")).all()
    assert [row[0] for row in rows] == ["e1"]


def test_verify_rejects_a_store_with_no_schema(store_url: str) -> None:
    engine = create_store_engine(store_url)
    with pytest.raises(StoreSchemaError, match="init-store"):
        schema.verify_revision(engine)


def test_verify_rejects_a_store_behind_head(
    store_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulates the next release: code at 0002, store still at 0001."""
    engine = create_store_engine(store_url)
    schema.upgrade(engine)
    at = schema.current_revision(engine)
    assert at is not None

    monkeypatch.setattr(schema, "head_revision", lambda: "0002")
    monkeypatch.setattr(
        schema, "history", lambda: [(at, "baseline"), ("0002", "next release")]
    )

    with pytest.raises(StoreSchemaError, match="store upgrade"):
        schema.verify_revision(engine)


def test_verify_rejects_a_store_ahead_of_the_code(store_url: str) -> None:
    """Old code against a newer store must refuse, not silently misread it."""
    engine = create_store_engine(store_url)
    schema.upgrade(engine)
    with engine.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num = '9999'"))

    with pytest.raises(StoreSchemaError, match="newer bizkit"):
        schema.verify_revision(engine)


def test_the_app_refuses_to_start_on_an_unmigrated_store(store_url: str) -> None:
    """`create_app` verifies but never migrates (D45)."""
    with pytest.raises(StoreSchemaError):
        create_app(BizkitConfig(store_url=store_url))

    engine = create_store_engine(store_url)
    assert schema.current_revision(engine) is None, "startup must not have migrated"


def test_ready_reports_the_store_revision(
    store_url: str, migrate_store: Callable[[str], None]
) -> None:
    from fastapi.testclient import TestClient

    migrate_store(store_url)
    with TestClient(create_app(BizkitConfig(store_url=store_url))) as client:
        body = client.get("/api/ready").json()

    assert body["store_revision"] == schema.head_revision()
    assert body["store_up_to_date"] is True
    assert body["status"] == "ready"


def test_offline_sql_emits_ddl_without_touching_the_database(
    store_url: str, tmp_path: Path
) -> None:
    """The DBA-applied path: DDL out, no connection, no schema created."""
    import io

    buffer = io.StringIO()
    schema.emit_sql(store_url, stream=buffer)
    ddl = buffer.getvalue()

    assert "CREATE TABLE bizkit_changesets" in ddl
    assert "CREATE TABLE alembic_version" in ddl
    assert not (tmp_path / "store.db").exists()


def test_stamp_records_an_out_of_band_upgrade(store_url: str) -> None:
    """After a DBA applies the emitted DDL, stamping is what records it."""
    engine = create_store_engine(store_url)
    from bizkit.store.models import Base

    Base.metadata.create_all(engine)

    schema.stamp(engine, schema.head_revision())

    schema.verify_revision(engine)


def test_history_lists_the_chain_oldest_first() -> None:
    chain = schema.history()
    assert chain[0][0] == "0001"
    assert [revision for revision, _ in chain] == sorted(
        revision for revision, _ in chain
    )
