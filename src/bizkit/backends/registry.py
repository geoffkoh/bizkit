"""Backend name → class registry with lazy imports (spec D3)."""

import importlib
from typing import Final

from bizkit.backends.base import BaseBackend
from bizkit.exceptions import UnknownBackendError

_BACKEND_PATHS: Final[dict[str, str]] = {
    "oracle": "bizkit.backends.oracle:OracleBackend",
    "mssql": "bizkit.backends.mssql:MSSQLBackend",
    "mysql": "bizkit.backends.mysql:MySQLBackend",
    "percona": "bizkit.backends.mysql:MySQLBackend",
    "postgres": "bizkit.backends.postgres:PostgresBackend",
    "snowflake": "bizkit.backends.snowflake:SnowflakeBackend",
    "databricks": "bizkit.backends.databricks:DatabricksBackend",
    # Dev-only demo backend (D39) — not an enterprise target.
    "sqlite": "bizkit.backends.sqlite:SqliteBackend",
}


def available_backends() -> list[str]:
    """Return the registered backend names (sorted)."""
    return sorted(_BACKEND_PATHS)


def get_backend_class(name: str) -> type[BaseBackend]:
    """Resolve a backend name to its adapter class.

    The adapter module imports cleanly without its driver; the driver is
    checked lazily on first engine use (D3).

    Args:
        name: Registered backend name (``percona`` aliases ``mysql``, D4).

    Returns:
        The adapter class.

    Raises:
        UnknownBackendError: If the name is not registered.
    """
    try:
        path = _BACKEND_PATHS[name]
    except KeyError:
        known = ", ".join(available_backends())
        raise UnknownBackendError(
            f"Unknown backend {name!r}. Known backends: {known}"
        ) from None
    module_name, _, class_name = path.partition(":")
    module = importlib.import_module(module_name)
    backend_class: type[BaseBackend] = getattr(module, class_name)
    return backend_class
