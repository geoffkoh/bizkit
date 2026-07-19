"""Table and column metadata for configuration tables."""

from pydantic import BaseModel


class TableRef(BaseModel):
    """Reference to a configuration table in a target database.

    Attributes:
        backend: Registered backend name the table lives in.
        schema_name: Optional schema/namespace qualifier.
        table: Table name.
    """

    backend: str
    schema_name: str | None = None
    table: str

    def qualified_name(self) -> str:
        """Return ``schema.table`` or just ``table`` when unqualified."""
        if self.schema_name:
            return f"{self.schema_name}.{self.table}"
        return self.table


class ColumnSpec(BaseModel):
    """Column description in bizkit's canonical type vocabulary.

    Attributes:
        name: Column name.
        type: Canonical type (see :mod:`bizkit.backends.typemap`).
        nullable: Whether NULL is allowed.
        primary_key: Whether the column is part of the primary key.
    """

    name: str
    type: str
    nullable: bool = True
    primary_key: bool = False
