"""Engine and session factories for the workflow store.

Sync SQLAlchemy only (spec D2). Schema creation via ``create_all`` is a
dev-only path; Alembic migrations are a pre-GA gate (D34).
"""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from bizkit.store.models import Base


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


def create_schema(engine: Engine) -> None:
    """Create the store schema (dev-only path; see spec D34)."""
    Base.metadata.create_all(engine)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Build a session factory bound to the store engine."""
    return sessionmaker(bind=engine, expire_on_commit=False)
