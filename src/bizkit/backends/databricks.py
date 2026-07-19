"""Databricks target backend.

Dialect notes: Delta tables; no multi-statement transactions — apply
must be write-then-verify with explicit reconciliation reported via
``ApplyError`` on partial application. Driver: databricks-sqlalchemy
(`bizkit[databricks]`).
"""

from typing import ClassVar

from bizkit.backends.base import BaseBackend


class DatabricksBackend(BaseBackend):
    """Databricks adapter."""

    name: ClassVar[str] = "databricks"
    extra: ClassVar[str] = "databricks"
    driver_module: ClassVar[str] = "databricks.sqlalchemy"
