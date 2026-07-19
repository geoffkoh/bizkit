"""Repository implementations over the workflow store.

Implements the ports from :mod:`bizkit.domain.ports`. Changeset updates
are compare-and-set on ``lock_version`` (spec D31): the first writer wins
and the loser gets :class:`~bizkit.exceptions.ConcurrencyError` — never a
double transition or duplicate audit event.
"""

from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session

from bizkit.domain.approval import ReviewDecision
from bizkit.domain.audit import AuditEvent
from bizkit.domain.changeset import Changeset
from bizkit.domain.comment import Comment
from bizkit.exceptions import ConcurrencyError, StoreError
from bizkit.store.models import (
    AuditEventRecord,
    ChangesetRecord,
    CommentRecord,
    ReviewDecisionRecord,
)


class SqlAlchemyChangesetRepository:
    """Changeset persistence with optimistic locking (D31)."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._lock_versions: dict[str, int] = {}

    def add(self, changeset: Changeset) -> None:
        """Persist a new changeset at lock_version 0."""
        self._session.add(
            ChangesetRecord(
                id=changeset.id,
                state=changeset.state.value,
                maker=changeset.maker,
                lock_version=0,
                payload=changeset.model_dump(mode="json"),
            )
        )
        self._session.flush()
        self._lock_versions[changeset.id] = 0

    def get(self, changeset_id: str) -> Changeset:
        """Load a changeset, caching its lock version for CAS updates."""
        record = self._session.get(ChangesetRecord, changeset_id)
        if record is None:
            raise StoreError(f"Changeset {changeset_id} not found")
        self._lock_versions[changeset_id] = record.lock_version
        return Changeset.model_validate(record.payload)

    def list(self) -> list[Changeset]:
        """Return all changesets."""
        records = self._session.scalars(select(ChangesetRecord)).all()
        return [Changeset.model_validate(r.payload) for r in records]

    def update(self, changeset: Changeset) -> None:
        """Compare-and-set update; raises on optimistic-lock conflict.

        Raises:
            StoreError: If the changeset was never loaded through this
                repository (no lock version to compare against).
            ConcurrencyError: If another writer updated the row first.
        """
        expected = self._lock_versions.get(changeset.id)
        if expected is None:
            raise StoreError(f"Changeset {changeset.id} must be loaded before update")
        result = cast(
            "CursorResult[Any]",
            self._session.execute(
                update(ChangesetRecord)
                .where(
                    ChangesetRecord.id == changeset.id,
                    ChangesetRecord.lock_version == expected,
                )
                .values(
                    state=changeset.state.value,
                    maker=changeset.maker,
                    lock_version=expected + 1,
                    payload=changeset.model_dump(mode="json"),
                )
            ),
        )
        if result.rowcount != 1:
            raise ConcurrencyError(
                f"Changeset {changeset.id} was modified concurrently "
                f"(expected lock_version {expected})"
            )
        self._lock_versions[changeset.id] = expected + 1


class SqlAlchemyDecisionRepository:
    """Review-decision persistence."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, decision: ReviewDecision) -> None:
        """Persist a review decision."""
        self._session.add(
            ReviewDecisionRecord(
                changeset_id=decision.changeset_id,
                payload=decision.model_dump(mode="json"),
            )
        )
        self._session.flush()

    def list_for(self, changeset_id: str) -> list[ReviewDecision]:
        """Return a changeset's decisions in creation order."""
        records = self._session.scalars(
            select(ReviewDecisionRecord)
            .where(ReviewDecisionRecord.changeset_id == changeset_id)
            .order_by(ReviewDecisionRecord.seq)
        ).all()
        return [ReviewDecision.model_validate(r.payload) for r in records]


class SqlAlchemyCommentRepository:
    """Comment persistence."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, comment: Comment) -> None:
        """Persist a comment."""
        self._session.add(
            CommentRecord(
                id=comment.id,
                changeset_id=comment.changeset_id,
                payload=comment.model_dump(mode="json"),
            )
        )
        self._session.flush()

    def list_for(self, changeset_id: str) -> list[Comment]:
        """Return a changeset's comments in creation order."""
        records = self._session.scalars(
            select(CommentRecord).where(CommentRecord.changeset_id == changeset_id)
        ).all()
        comments = [Comment.model_validate(r.payload) for r in records]
        return sorted(comments, key=lambda c: c.created_at)


class SqlAlchemyAuditLog:
    """Append-only audit log (D10/D35): no update or delete paths exist."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, event: AuditEvent) -> None:
        """Append an event in the caller's transaction."""
        self._session.add(
            AuditEventRecord(
                event_id=event.id,
                changeset_id=event.changeset_id,
                payload=event.model_dump(mode="json"),
            )
        )
        self._session.flush()

    def list_for(self, changeset_id: str) -> list[AuditEvent]:
        """Return a changeset's events in append order."""
        records = self._session.scalars(
            select(AuditEventRecord)
            .where(AuditEventRecord.changeset_id == changeset_id)
            .order_by(AuditEventRecord.seq)
        ).all()
        return [AuditEvent.model_validate(r.payload) for r in records]
