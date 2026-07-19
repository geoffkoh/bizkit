"""Oracle target backend.

Dialect notes: no transactional DDL; empty string is NULL (affects
not-null validation semantics); identifiers fold to uppercase; older
versions cap identifier names at 30 bytes. Driver: python-oracledb
(`bizkit[oracle]`).
"""

from typing import ClassVar

from bizkit.backends.base import BaseBackend


class OracleBackend(BaseBackend):
    """Oracle adapter."""

    name: ClassVar[str] = "oracle"
    extra: ClassVar[str] = "oracle"
    driver_module: ClassVar[str] = "oracledb"
