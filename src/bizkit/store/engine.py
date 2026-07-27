"""Engine and session factories for the workflow store.

Sync SQLAlchemy only (spec D2). The schema itself is owned by the Alembic
chain in :mod:`bizkit.store.schema` (D45) — there is deliberately no
``create_all`` here, because it silently skips existing tables and so cannot
serve as an upgrade path.
"""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def create_store_engine(url: str) -> Engine:
    """Create the sync engine for the workflow store.

    In-memory SQLite gets a shared static pool so all sessions (and API
    threadpool workers) see one database.

    Args:
        url: SQLAlchemy URL of the store.

    Returns:
        A configured sync engine.
    """
    if url.endswith(":memory:"):
        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(url)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Build a session factory bound to the store engine."""
    return sessionmaker(bind=engine, expire_on_commit=False)
