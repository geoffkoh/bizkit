"""The sqlite demo backend's read path (spec D39)."""

import sqlite3
from pathlib import Path

import pytest

from bizkit.backends.sqlite import SqliteBackend
from bizkit.domain.changeset import ChangeItem, ChangeOp, Changeset, ChangesetState
from bizkit.domain.table import TableRef
from bizkit.exceptions import ApplyError


@pytest.fixture
def sample_db(tmp_path: Path) -> Path:
    path = tmp_path / "target.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE fx_rates (pair TEXT PRIMARY KEY, rate REAL NOT NULL)"
        )
        conn.execute("INSERT INTO fx_rates VALUES ('EURUSD', 1.09), ('GBPUSD', 1.27)")
        conn.commit()
    return path


def test_introspect_table(sample_db: Path) -> None:
    backend = SqliteBackend(f"sqlite:///{sample_db}")
    columns = backend.introspect_table(TableRef(backend="t", table="fx_rates"))
    by_name = {c.name: c for c in columns}
    assert by_name["pair"].type == "string"
    assert by_name["pair"].primary_key is True
    assert by_name["rate"].type == "decimal"
    assert by_name["rate"].nullable is False


def test_read_rows(sample_db: Path) -> None:
    backend = SqliteBackend(f"sqlite:///{sample_db}")
    rows = backend.read_rows(TableRef(backend="t", table="fx_rates"), ["pair", "rate"])
    assert {"pair": "EURUSD", "rate": 1.09} in rows
    assert len(rows) == 2


# -- write path: dry_run and apply (spec §5) ------------------------------
#
# The DML itself lives in BaseBackend on SQLAlchemy Core, so every dialect
# inherits one implementation; these tests exercise it through the sqlite
# adapter. The invariants under test are cross-dialect: all-or-nothing,
# dry_run leaves the target untouched, and a row-count mismatch is drift
# rather than something to paper over.

FX = TableRef(backend="t", table="fx_rates")


def approved(items: list[ChangeItem]) -> Changeset:
    """An APPROVED changeset — the only state apply accepts."""
    changeset = Changeset(table=FX, maker="alice", title="c", items=items)
    changeset.state = ChangesetState.APPROVED
    return changeset


def rows(db: Path) -> dict[str, float]:
    with sqlite3.connect(db) as conn:
        return dict(conn.execute("SELECT pair, rate FROM fx_rates").fetchall())


def test_apply_inserts_a_row(sample_db: Path) -> None:
    backend = SqliteBackend(f"sqlite:///{sample_db}")
    backend.apply(
        approved(
            [ChangeItem(op=ChangeOp.INSERT, values={"pair": "USDJPY", "rate": 155.2})]
        )
    )
    assert rows(sample_db)["USDJPY"] == 155.2


def test_apply_updates_a_row(sample_db: Path) -> None:
    backend = SqliteBackend(f"sqlite:///{sample_db}")
    backend.apply(
        approved(
            [
                ChangeItem(
                    op=ChangeOp.UPDATE, key={"pair": "EURUSD"}, values={"rate": 1.11}
                )
            ]
        )
    )
    assert rows(sample_db)["EURUSD"] == 1.11


def test_apply_deletes_a_row(sample_db: Path) -> None:
    backend = SqliteBackend(f"sqlite:///{sample_db}")
    backend.apply(approved([ChangeItem(op=ChangeOp.DELETE, key={"pair": "GBPUSD"})]))
    assert "GBPUSD" not in rows(sample_db)


def test_apply_is_all_or_nothing(sample_db: Path) -> None:
    # Second item targets a row that is not there; the first must not survive.
    backend = SqliteBackend(f"sqlite:///{sample_db}")
    changeset = approved(
        [
            ChangeItem(op=ChangeOp.INSERT, values={"pair": "USDJPY", "rate": 155.2}),
            ChangeItem(op=ChangeOp.UPDATE, key={"pair": "NOPE"}, values={"rate": 1.0}),
        ]
    )
    with pytest.raises(ApplyError):
        backend.apply(changeset)
    assert "USDJPY" not in rows(sample_db)


def test_dry_run_leaves_the_target_unchanged(sample_db: Path) -> None:
    backend = SqliteBackend(f"sqlite:///{sample_db}")
    before = rows(sample_db)
    backend.dry_run(
        approved(
            [
                ChangeItem(
                    op=ChangeOp.INSERT, values={"pair": "USDJPY", "rate": 155.2}
                ),
                ChangeItem(
                    op=ChangeOp.UPDATE, key={"pair": "EURUSD"}, values={"rate": 9.99}
                ),
                ChangeItem(op=ChangeOp.DELETE, key={"pair": "GBPUSD"}),
            ]
        )
    )
    assert rows(sample_db) == before


def test_dry_run_surfaces_the_error_apply_would_hit(sample_db: Path) -> None:
    backend = SqliteBackend(f"sqlite:///{sample_db}")
    with pytest.raises(ApplyError):
        backend.dry_run(
            approved(
                [ChangeItem(op=ChangeOp.INSERT, values={"pair": "EURUSD", "rate": 1.0})]
            )
        )


def test_update_of_a_vanished_row_is_reported_as_drift(sample_db: Path) -> None:
    backend = SqliteBackend(f"sqlite:///{sample_db}")
    with pytest.raises(ApplyError, match="0 rows"):
        backend.apply(
            approved(
                [
                    ChangeItem(
                        op=ChangeOp.UPDATE, key={"pair": "NOPE"}, values={"rate": 1.0}
                    )
                ]
            )
        )


def test_delete_of_a_vanished_row_is_reported_as_drift(sample_db: Path) -> None:
    backend = SqliteBackend(f"sqlite:///{sample_db}")
    with pytest.raises(ApplyError, match="0 rows"):
        backend.apply(approved([ChangeItem(op=ChangeOp.DELETE, key={"pair": "NOPE"})]))


def test_unknown_column_is_reported_clearly(sample_db: Path) -> None:
    backend = SqliteBackend(f"sqlite:///{sample_db}")
    with pytest.raises(ApplyError, match="not a column"):
        backend.apply(
            approved([ChangeItem(op=ChangeOp.INSERT, values={"nope": 1, "pair": "X"})])
        )


def test_apply_refuses_a_changeset_that_is_not_approved(sample_db: Path) -> None:
    # Defense in depth: the service guards state, and so does the backend.
    backend = SqliteBackend(f"sqlite:///{sample_db}")
    draft = Changeset(
        table=FX,
        maker="alice",
        title="c",
        items=[ChangeItem(op=ChangeOp.INSERT, values={"pair": "USDJPY", "rate": 1.0})],
    )
    with pytest.raises(ApplyError, match="draft"):
        backend.apply(draft)
    assert "USDJPY" not in rows(sample_db)


def test_apply_accepts_a_failed_changeset_as_a_retry(sample_db: Path) -> None:
    # FAILED -> APPLIED is the retry of an already-approved revision (D20).
    backend = SqliteBackend(f"sqlite:///{sample_db}")
    changeset = approved(
        [ChangeItem(op=ChangeOp.INSERT, values={"pair": "USDJPY", "rate": 1.0})]
    )
    changeset.state = ChangesetState.FAILED
    backend.apply(changeset)
    assert "USDJPY" in rows(sample_db)


def test_update_needs_a_key(sample_db: Path) -> None:
    backend = SqliteBackend(f"sqlite:///{sample_db}")
    with pytest.raises(ApplyError, match="key"):
        backend.apply(approved([ChangeItem(op=ChangeOp.UPDATE, values={"rate": 1.0})]))


def test_empty_changeset_applies_as_a_no_op(sample_db: Path) -> None:
    backend = SqliteBackend(f"sqlite:///{sample_db}")
    before = rows(sample_db)
    backend.apply(approved([]))
    assert rows(sample_db) == before
