"""MySQL target backend — also serves Percona (spec D4).

Dialect notes: DDL causes an implicit commit, so dry-run must never emit
DDL inside its rehearsal transaction; use utf8mb4, never utf8. Percona is
wire-compatible and rides this adapter via the ``percona`` registry
alias. Driver: PyMySQL (`bizkit[mysql]`).
"""

from typing import ClassVar

from bizkit.backends.base import BaseBackend


class MySQLBackend(BaseBackend):
    """MySQL/Percona adapter."""

    name: ClassVar[str] = "mysql"
    extra: ClassVar[str] = "mysql"
    driver_module: ClassVar[str] = "pymysql"
