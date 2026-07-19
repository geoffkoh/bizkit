"""PostgreSQL target backend.

Dialect notes: transactional DDL — the well-behaved reference
implementation; dry-run can use a plain transaction rollback. Driver:
psycopg 3 (`bizkit[postgres]`).
"""

from typing import ClassVar

from bizkit.backends.base import BaseBackend


class PostgresBackend(BaseBackend):
    """PostgreSQL adapter (reference implementation)."""

    name: ClassVar[str] = "postgres"
    extra: ClassVar[str] = "postgres"
    driver_module: ClassVar[str] = "psycopg"
