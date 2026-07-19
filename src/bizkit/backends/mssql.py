"""MSSQL target backend.

Dialect notes: pyodbc DSN/driver strings required in URLs; IDENTITY
columns need explicit ``SET IDENTITY_INSERT`` for keyed inserts; locking
behavior differs between snapshot and read-committed isolation. Driver:
pyodbc (`bizkit[mssql]`).
"""

from typing import ClassVar

from bizkit.backends.base import BaseBackend


class MSSQLBackend(BaseBackend):
    """MSSQL adapter."""

    name: ClassVar[str] = "mssql"
    extra: ClassVar[str] = "mssql"
    driver_module: ClassVar[str] = "pyodbc"
