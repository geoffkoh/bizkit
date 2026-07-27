"""Store schema lifecycle: Alembic migrations (spec D46).

The store's schema is owned by the forward-only migration chain in
``migrations/versions/``, shipped inside the wheel. Creating a fresh store
and upgrading an existing one are the same operation — ``upgrade`` against
an empty database — so dev and production never take divergent paths.

Nothing here runs implicitly. The API and CLI call :func:`verify_revision`
and refuse to start on a mismatch; only ``bizkit init-store`` and
``bizkit store upgrade`` migrate, deliberately, with a credential that has
DDL rights (D29).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, TextIO

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine

from bizkit.exceptions import StoreSchemaError

INI_PATH = Path(__file__).with_name("alembic.ini")


def _config(
    *,
    url: str | None = None,
    connection: Connection | None = None,
    stdout: TextIO | None = None,
) -> Config:
    """Build an Alembic config pointed at the packaged migration chain.

    Args:
        url: Store URL, injected at runtime rather than written to the ini.
        connection: Open connection for the migration to borrow, so callers
            can migrate an in-memory SQLite store or supply their own
            transaction.
        stdout: Stream for ``--sql`` output; defaults to real stdout.

    Returns:
        A configured Alembic ``Config``.
    """
    # output_buffer is what offline (--sql) DDL is written to; stdout covers
    # Alembic's own chatter. Both are redirected so callers can capture.
    cfg = Config(
        str(INI_PATH),
        output_buffer=stdout,
        stdout=stdout or sys.stdout,
    )
    if url is not None:
        cfg.attributes["url"] = url
    if connection is not None:
        cfg.attributes["connection"] = connection
    return cfg


def head_revision() -> str:
    """Return the head revision this build of bizkit expects.

    Returns:
        The head revision id.

    Raises:
        StoreSchemaError: If the packaged migration chain has no head (a
            broken build) or branches (an unmerged revision).
    """
    heads = ScriptDirectory.from_config(_config()).get_heads()
    if len(heads) != 1:
        raise StoreSchemaError(
            f"Expected exactly one migration head, found {len(heads)}: "
            f"{', '.join(heads) or 'none'}."
        )
    return heads[0]


def current_revision(engine: Engine) -> str | None:
    """Return the revision a store is stamped at.

    Args:
        engine: Engine bound to the workflow store.

    Returns:
        The revision id, or ``None`` for a database with no
        ``alembic_version`` row (never migrated).
    """
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def upgrade(engine: Engine, revision: str = "head") -> None:
    """Migrate a store forward, creating it if it does not exist yet.

    Args:
        engine: Engine bound to the workflow store; the connection is
            borrowed so in-memory SQLite works.
        revision: Target revision; defaults to head.
    """
    with engine.begin() as connection:
        command.upgrade(_config(connection=connection), revision)


def emit_sql(url: str, revision: str = "head", stream: TextIO | None = None) -> None:
    """Write the upgrade DDL without touching a database (D46 offline mode).

    Args:
        url: Store URL — used for dialect selection only; no connection is
            opened.
        revision: Target revision, or a ``from:to`` range.
        stream: Destination for the DDL; defaults to stdout.
    """
    command.upgrade(_config(url=url, stdout=stream), revision, sql=True)


def stamp(engine: Engine, revision: str = "head") -> None:
    """Record a revision as applied without running it.

    For stores upgraded out of band by a DBA from :func:`emit_sql` output.

    Args:
        engine: Engine bound to the workflow store.
        revision: Revision to stamp.
    """
    with engine.begin() as connection:
        command.stamp(_config(connection=connection), revision)


def history() -> list[tuple[str, str]]:
    """List the migration chain, oldest first.

    Returns:
        ``(revision, description)`` pairs.
    """
    scripts = ScriptDirectory.from_config(_config())
    return [
        (script.revision, script.doc)
        for script in reversed(list(scripts.walk_revisions()))
    ]


def verify_revision(engine: Engine) -> None:
    """Check a store's schema against this build, without changing it.

    bizkit never migrates as a side effect of starting (D46): an operator
    runs the upgrade deliberately, so a mismatch is a startup failure.

    Args:
        engine: Engine bound to the workflow store.

    Raises:
        StoreSchemaError: If the store has never been migrated, is behind
            head, or is *ahead* of it (code older than the store).
    """
    head = head_revision()
    current = current_revision(engine)
    if current == head:
        return
    if current is None:
        raise StoreSchemaError(
            "The workflow store has no schema. Create it with 'bizkit init-store'."
        )

    known = {revision for revision, _ in history()}
    if current not in known:
        raise StoreSchemaError(
            f"The workflow store is at revision {current}, which this build of "
            f"bizkit does not know (its head is {head}). The store was "
            "migrated by a newer bizkit; upgrade the application instead of "
            "downgrading the store."
        )
    raise StoreSchemaError(
        f"The workflow store is at revision {current}, behind this build's "
        f"head {head}. Run 'bizkit store upgrade' (or 'bizkit store upgrade "
        "--sql' to hand the DDL to a DBA)."
    )


def describe(engine: Engine) -> dict[str, Any]:
    """Summarize schema state for readiness reporting.

    Args:
        engine: Engine bound to the workflow store.

    Returns:
        Mapping with ``current``, ``head``, and ``up_to_date``.
    """
    head = head_revision()
    current = current_revision(engine)
    return {"current": current, "head": head, "up_to_date": current == head}
