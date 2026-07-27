"""Alembic environment for the bizkit workflow store (spec D46).

Runs in three modes:

* **Online, borrowed connection** — ``config.attributes["connection"]`` is
  set by :mod:`bizkit.store.schema`. Required for in-memory SQLite (a new
  engine would see an empty database) and lets a caller wrap the upgrade in
  its own transaction.
* **Online, own engine** — built from the URL in ``config.attributes["url"]``
  or ``sqlalchemy.url``.
* **Offline (``--sql``)** — emits DDL to stdout and touches no database, for
  deployments where a DBA applies schema changes from a ticket (D46).

``render_as_batch`` is on because the dev store is SQLite, which cannot
``ALTER`` most things in place and needs Alembic's copy-and-move rebuild.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import Connection, engine_from_config, pool

from bizkit.store.models import Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    """Resolve the store URL from runtime attributes or the ini file."""
    url = config.attributes.get("url") or config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError(
            "No store URL configured for the migration environment; "
            "pass one via bizkit.store.schema."
        )
    return str(url)


def _run(connection: Connection) -> None:
    """Configure the migration context against an open connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Emit DDL without a database connection (``--sql``)."""
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations against a live database."""
    borrowed = config.attributes.get("connection")
    if borrowed is not None:
        _run(borrowed)
        return

    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _url()
    engine = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            _run(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
