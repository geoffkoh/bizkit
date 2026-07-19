"""Workflow metadata store: sync SQLAlchemy persistence (spec D1/D2/D29).

Holds operational state — changesets, review decisions, comments, audit
events. Separation from targets is logical: own database/schema and
credentials, OLTP engine only (D29). Optional store-backed config
adapters (grants/table registry) land with the runtime-administration
milestone (D22).
"""

from bizkit.store.engine import (
    create_schema,
    create_session_factory,
    create_store_engine,
)
from bizkit.store.repositories import (
    SqlAlchemyAuditLog,
    SqlAlchemyChangesetRepository,
    SqlAlchemyCommentRepository,
    SqlAlchemyDecisionRepository,
)

__all__ = [
    "SqlAlchemyAuditLog",
    "SqlAlchemyChangesetRepository",
    "SqlAlchemyCommentRepository",
    "SqlAlchemyDecisionRepository",
    "create_schema",
    "create_session_factory",
    "create_store_engine",
]
