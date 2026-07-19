"""Canonical type ↔ dialect type mapping (spec §5).

Canonical types: ``string``, ``integer``, ``decimal``, ``boolean``,
``date``, ``timestamp``. Mappings are bidirectional and covered by tests
for all backends.
"""

from typing import Final

from bizkit.exceptions import BizkitError, UnknownBackendError

CANONICAL_TYPES: Final[frozenset[str]] = frozenset(
    {"string", "integer", "decimal", "boolean", "date", "timestamp"}
)

_DIALECT_TYPES: Final[dict[str, dict[str, str]]] = {
    "oracle": {
        "string": "VARCHAR2",
        "integer": "NUMBER(19)",
        "decimal": "NUMBER",
        "boolean": "NUMBER(1)",
        "date": "DATE",
        "timestamp": "TIMESTAMP WITH TIME ZONE",
    },
    "mssql": {
        "string": "NVARCHAR",
        "integer": "BIGINT",
        "decimal": "DECIMAL",
        "boolean": "BIT",
        "date": "DATE",
        "timestamp": "DATETIMEOFFSET",
    },
    "mysql": {
        "string": "VARCHAR",
        "integer": "BIGINT",
        "decimal": "DECIMAL",
        "boolean": "TINYINT(1)",
        "date": "DATE",
        "timestamp": "TIMESTAMP",
    },
    "postgres": {
        "string": "VARCHAR",
        "integer": "BIGINT",
        "decimal": "NUMERIC",
        "boolean": "BOOLEAN",
        "date": "DATE",
        "timestamp": "TIMESTAMP WITH TIME ZONE",
    },
    "snowflake": {
        "string": "VARCHAR",
        "integer": "NUMBER(38,0)",
        "decimal": "NUMBER",
        "boolean": "BOOLEAN",
        "date": "DATE",
        "timestamp": "TIMESTAMP_TZ",
    },
    "databricks": {
        "string": "STRING",
        "integer": "BIGINT",
        "decimal": "DECIMAL",
        "boolean": "BOOLEAN",
        "date": "DATE",
        "timestamp": "TIMESTAMP",
    },
    # Dev-only demo backend (D39).
    "sqlite": {
        "string": "TEXT",
        "integer": "INTEGER",
        "decimal": "REAL",
        "boolean": "BOOLEAN",
        "date": "DATE",
        "timestamp": "TIMESTAMP",
    },
}


def to_dialect(canonical: str, backend: str) -> str:
    """Map a canonical type to the backend's dialect type.

    Args:
        canonical: One of :data:`CANONICAL_TYPES`.
        backend: Backend technology name (``percona`` uses ``mysql``).

    Returns:
        The dialect type name.

    Raises:
        UnknownBackendError: If the backend is not mapped.
        BizkitError: If the canonical type is unknown.
    """
    backend_key = "mysql" if backend == "percona" else backend
    try:
        mapping = _DIALECT_TYPES[backend_key]
    except KeyError:
        raise UnknownBackendError(f"No type mapping for backend {backend!r}") from None
    try:
        return mapping[canonical]
    except KeyError:
        raise BizkitError(
            f"Unknown canonical type {canonical!r}; expected one of "
            f"{sorted(CANONICAL_TYPES)}"
        ) from None


def to_canonical(dialect_type: str, backend: str) -> str:
    """Map a dialect type back to its canonical type.

    Args:
        dialect_type: Dialect type name (case-insensitive).
        backend: Backend technology name (``percona`` uses ``mysql``).

    Returns:
        The canonical type name.

    Raises:
        UnknownBackendError: If the backend is not mapped.
        BizkitError: If the dialect type has no canonical mapping.
    """
    backend_key = "mysql" if backend == "percona" else backend
    try:
        mapping = _DIALECT_TYPES[backend_key]
    except KeyError:
        raise UnknownBackendError(f"No type mapping for backend {backend!r}") from None
    wanted = dialect_type.strip().upper()
    for canonical, dialect in mapping.items():
        if dialect.upper() == wanted:
            return canonical
    raise BizkitError(f"No canonical mapping for {backend!r} type {dialect_type!r}")
