"""Workflow metadata store: sync SQLAlchemy persistence (spec D1/D2/D29).

Holds operational state — changesets, review decisions, comments, audit
events. Separation from targets is logical: own database/schema and
credentials, OLTP engine only (D29). The schema is owned by forward-only
Alembic migrations (D46): :mod:`bizkit.store.schema` upgrades it explicitly
and verifies it at startup — nothing here creates tables implicitly.
Optional store-backed config adapters (grants/table registry) land with the
runtime-administration milestone (D22).
"""

from bizkit.store.engine import (
    create_session_factory,
    create_store_engine,
)
from bizkit.store.repositories import (
    SqlAlchemyAuditLog,
    SqlAlchemyChangesetRepository,
    SqlAlchemyCommentRepository,
    SqlAlchemyDecisionRepository,
)
from bizkit.store.schema import (
    current_revision,
    describe,
    head_revision,
    upgrade,
    verify_revision,
)

__all__ = [
    "SqlAlchemyAuditLog",
    "SqlAlchemyChangesetRepository",
    "SqlAlchemyCommentRepository",
    "SqlAlchemyDecisionRepository",
    "create_session_factory",
    "create_store_engine",
    "current_revision",
    "describe",
    "head_revision",
    "upgrade",
    "verify_revision",
]
