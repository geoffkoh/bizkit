"""SQLite demo backend (spec D39).

A dev-only backend — NOT an enterprise target. It exists so the table
browser works out of the box against the seeded sample database and as
the first test vehicle for the backend contract. The driver is the
stdlib ``sqlite3`` module, so no optional extra is involved.

Dialect notes: dynamic typing (declared column types are affinities,
not constraints); schemas are attached databases (usually ``None``);
transactional DDL supported.
"""

from collections.abc import Sequence
from typing import ClassVar

from sqlalchemy import inspect, text

from bizkit.domain.table import ColumnSpec, TableRef

from bizkit.backends.base import BaseBackend

_AFFINITY_TO_CANONICAL: dict[str, str] = {
    "INT": "integer",
    "CHAR": "string",
    "TEXT": "string",
    "CLOB": "string",
    "REAL": "decimal",
    "FLOA": "decimal",
    "DOUB": "decimal",
    "NUMERIC": "decimal",
    "DECIMAL": "decimal",
    "BOOL": "boolean",
    "DATETIME": "timestamp",
    "TIMESTAMP": "timestamp",
    "DATE": "date",
}


def _canonical_type(declared: str) -> str:
    upper = declared.upper()
    for fragment, canonical in _AFFINITY_TO_CANONICAL.items():
        if fragment in upper:
            return canonical
    return "string"


class SqliteBackend(BaseBackend):
    """SQLite adapter with a working read path (introspect + read_rows)."""

    name: ClassVar[str] = "sqlite"
    extra: ClassVar[str] = ""
    driver_module: ClassVar[str] = "sqlite3"

    def introspect_table(self, ref: TableRef) -> list[ColumnSpec]:
        """Describe the table via SQLAlchemy inspection."""
        inspector = inspect(self.engine)
        columns = inspector.get_columns(ref.table, schema=ref.schema_name)
        pk = set(
            inspector.get_pk_constraint(ref.table, schema=ref.schema_name).get(
                "constrained_columns", []
            )
        )
        return [
            ColumnSpec(
                name=column["name"],
                type=_canonical_type(str(column["type"])),
                nullable=bool(column.get("nullable", True)),
                primary_key=column["name"] in pk,
            )
            for column in columns
        ]

    def read_rows(
        self, ref: TableRef, columns: Sequence[str]
    ) -> list[dict[str, object]]:
        """Read all rows (read-only, D13); identifiers are quoted."""
        column_sql = ", ".join(f'"{c}"' for c in columns)
        table_sql = (
            f'"{ref.schema_name}"."{ref.table}"'
            if ref.schema_name
            else f'"{ref.table}"'
        )
        with self.engine.connect() as connection:
            result = connection.execute(
                text(f"SELECT {column_sql} FROM {table_sql}")  # noqa: S608
            )
            return [dict(zip(columns, row, strict=True)) for row in result]
