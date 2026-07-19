"""The sqlite demo backend's read path (spec D39)."""

import sqlite3
from pathlib import Path

import pytest

from bizkit.backends.sqlite import SqliteBackend
from bizkit.domain.table import TableRef


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


def test_dry_run_still_unimplemented(sample_db: Path) -> None:
    backend = SqliteBackend(f"sqlite:///{sample_db}")
    with pytest.raises(NotImplementedError):
        backend.dry_run(None)  # type: ignore[arg-type]
