"""Snowflake target backend.

Dialect notes: FK/unique/check constraints are declared but NOT
enforced — dry-run must simulate them client-side; no classic row locks;
warehouses bill per-wakeup, so avoid chatty single-row round-trips.
Driver: snowflake-sqlalchemy (`bizkit[snowflake]`).
"""

from typing import ClassVar

from bizkit.backends.base import BaseBackend


class SnowflakeBackend(BaseBackend):
    """Snowflake adapter."""

    name: ClassVar[str] = "snowflake"
    extra: ClassVar[str] = "snowflake"
    driver_module: ClassVar[str] = "snowflake.sqlalchemy"
