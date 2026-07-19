"""ImportService: append + diff modes, all-or-nothing, cap, audit (D36)."""

import sqlite3
from pathlib import Path

import pytest

from bizkit.backends.sqlite import SqliteBackend
from bizkit.config import WorkflowConfig
from bizkit.domain.changeset import ChangeOp, Changeset, ChangesetState
from bizkit.domain.table import TableRef
from bizkit.exceptions import ChangesetLimitError, ChangesetStateError
from bizkit.services.importer import ImportMode, ImportService
from bizkit.store.repositories import (
    SqlAlchemyAuditLog,
    SqlAlchemyChangesetRepository,
)
from bizkit.workspace.access import FileAccessPolicy


@pytest.fixture
def target_db(tmp_path: Path) -> Path:
    path = tmp_path / "target.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE fx_rates (pair TEXT PRIMARY KEY, rate REAL NOT NULL)"
        )
        conn.execute("INSERT INTO fx_rates VALUES ('EURUSD', 1.09), ('GBPUSD', 1.27)")
        conn.commit()
    return path


@pytest.fixture
def importer(
    changeset_repo: SqlAlchemyChangesetRepository,
    audit_log: SqlAlchemyAuditLog,
    maker_checker_policy: FileAccessPolicy,
    target_db: Path,
) -> ImportService:
    backend = SqliteBackend(f"sqlite:///{target_db}")
    return ImportService(
        changesets=changeset_repo,
        audit=audit_log,
        access=maker_checker_policy,
        backend_for=lambda ref: backend,
    )


@pytest.fixture
def draft(
    changeset_repo: SqlAlchemyChangesetRepository, fx_table: TableRef
) -> Changeset:
    changeset = Changeset(table=fx_table, maker="alice", title="Bulk load")
    changeset_repo.add(changeset)
    return changeset


def test_append_mode_all_ops(
    importer: ImportService,
    draft: Changeset,
    changeset_repo: SqlAlchemyChangesetRepository,
    audit_log: SqlAlchemyAuditLog,
) -> None:
    csv_data = (
        "_op,pair,rate\ninsert,USDJPY,155.2\nupdate,EURUSD,1.10\ndelete,GBPUSD,\n"
    ).encode()
    report = importer.import_csv(
        draft.id, "alice", "rates.csv", csv_data, ImportMode.APPEND
    )
    assert report.ok, report.issues
    assert report.items_added == 3

    loaded = changeset_repo.get(draft.id)
    ops = [i.op for i in loaded.items]
    assert ops == [ChangeOp.INSERT, ChangeOp.UPDATE, ChangeOp.DELETE]
    assert loaded.items[0].values == {"pair": "USDJPY", "rate": 155.2}
    assert loaded.items[1].key == {"pair": "EURUSD"}
    assert loaded.items[1].values == {"rate": 1.10}
    assert loaded.items[2].key == {"pair": "GBPUSD"}

    events = audit_log.list_for(draft.id)
    assert events[-1].action == "import"
    assert "sha256:" in events[-1].detail
    assert "rows=3" in events[-1].detail


def test_missing_op_defaults_to_insert(
    importer: ImportService, draft: Changeset
) -> None:
    report = importer.import_csv(
        draft.id, "alice", "x.csv", b"pair,rate\nUSDNOK,10.5\n"
    )
    assert report.ok
    assert report.items_added == 1


def test_coercion_failure_is_all_or_nothing(
    importer: ImportService,
    draft: Changeset,
    changeset_repo: SqlAlchemyChangesetRepository,
    audit_log: SqlAlchemyAuditLog,
) -> None:
    csv_data = b"pair,rate\nUSDJPY,155.2\nUSDKRW,not-a-number\n"
    report = importer.import_csv(draft.id, "alice", "x.csv", csv_data)
    assert not report.ok
    assert report.items_added == 0
    assert report.issues[0].row == 2
    assert report.issues[0].column == "rate"
    assert changeset_repo.get(draft.id).items == []
    assert audit_log.list_for(draft.id) == []


def test_unknown_column_rejected(importer: ImportService, draft: Changeset) -> None:
    report = importer.import_csv(
        draft.id, "alice", "x.csv", b"pair,rate,bogus\nUSDJPY,155.2,zzz\n"
    )
    assert not report.ok
    assert report.issues[0].column == "bogus"


def test_diff_mode_computes_delta(
    importer: ImportService,
    draft: Changeset,
    changeset_repo: SqlAlchemyChangesetRepository,
) -> None:
    # Desired end state: EURUSD changed, GBPUSD absent (delete), USDJPY new.
    csv_data = b"pair,rate\nEURUSD,1.15\nUSDJPY,155.2\n"
    report = importer.import_csv(
        draft.id, "alice", "state.csv", csv_data, ImportMode.DIFF
    )
    assert report.ok, report.issues
    loaded = changeset_repo.get(draft.id)
    by_op = {i.op: i for i in loaded.items}
    assert by_op[ChangeOp.INSERT].values == {"pair": "USDJPY", "rate": 155.2}
    assert by_op[ChangeOp.UPDATE].key == {"pair": "EURUSD"}
    assert by_op[ChangeOp.UPDATE].values == {"rate": 1.15}
    assert by_op[ChangeOp.DELETE].key == {"pair": "GBPUSD"}
    assert len(loaded.items) == 3


def test_diff_identical_state_yields_no_items(
    importer: ImportService, draft: Changeset
) -> None:
    csv_data = b"pair,rate\nEURUSD,1.09\nGBPUSD,1.27\n"
    report = importer.import_csv(draft.id, "alice", "x.csv", csv_data, ImportMode.DIFF)
    assert report.ok
    assert report.items_added == 0


def test_cap_enforced(
    changeset_repo: SqlAlchemyChangesetRepository,
    audit_log: SqlAlchemyAuditLog,
    maker_checker_policy: FileAccessPolicy,
    target_db: Path,
    draft: Changeset,
) -> None:
    backend = SqliteBackend(f"sqlite:///{target_db}")
    importer = ImportService(
        changesets=changeset_repo,
        audit=audit_log,
        access=maker_checker_policy,
        config=WorkflowConfig(max_changeset_items=1),
        backend_for=lambda ref: backend,
    )
    csv_data = b"pair,rate\nUSDJPY,155.2\nUSDNOK,10.5\n"
    with pytest.raises(ChangesetLimitError):
        importer.import_csv(draft.id, "alice", "x.csv", csv_data)
    assert changeset_repo.get(draft.id).items == []


def test_import_requires_draft(
    importer: ImportService,
    draft: Changeset,
    changeset_repo: SqlAlchemyChangesetRepository,
) -> None:
    loaded = changeset_repo.get(draft.id)
    loaded.transition(ChangesetState.SUBMITTED)
    changeset_repo.update(loaded)
    with pytest.raises(ChangesetStateError):
        importer.import_csv(draft.id, "alice", "x.csv", b"pair,rate\nA,1\n")
