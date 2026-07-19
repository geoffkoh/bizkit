"""File-backed TableRegistry adapter (spec D22)."""

from bizkit.domain.table import TableRef
from bizkit.domain.table_config import TableConfig


class FileTableRegistry:
    """Resolves table references against workspace-file table configs."""

    def __init__(self, tables: list[TableConfig]) -> None:
        self._by_key = {
            (t.table.backend, t.table.schema_name, t.table.table): t for t in tables
        }

    def lookup(self, ref: TableRef) -> TableConfig | None:
        """Return the registered config for ``ref``, or ``None``."""
        return self._by_key.get((ref.backend, ref.schema_name, ref.table))
