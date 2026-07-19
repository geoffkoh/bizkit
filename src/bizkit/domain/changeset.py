"""Changeset aggregate and its state machine.

The transition table below is the single source of truth for the
maker-checker lifecycle (spec D9, D20, D21). Every state change must go
through :meth:`Changeset.transition`; services never mutate ``state``
directly.
"""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final

from pydantic import BaseModel, Field

from bizkit.domain.table import TableRef
from bizkit.exceptions import ChangesetStateError


class ChangeOp(StrEnum):
    """Kind of row-level change carried by a :class:`ChangeItem`."""

    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"


class ChangesetState(StrEnum):
    """Lifecycle states of a changeset."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    FAILED = "failed"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"


ALLOWED_TRANSITIONS: Final[dict[ChangesetState, frozenset[ChangesetState]]] = {
    ChangesetState.DRAFT: frozenset(
        {ChangesetState.SUBMITTED, ChangesetState.WITHDRAWN}
    ),
    ChangesetState.SUBMITTED: frozenset(
        {
            ChangesetState.APPROVED,
            ChangesetState.REJECTED,
            ChangesetState.WITHDRAWN,
            ChangesetState.EXPIRED,
        }
    ),
    ChangesetState.APPROVED: frozenset(
        {
            ChangesetState.APPLIED,
            ChangesetState.FAILED,
            ChangesetState.EXPIRED,
        }
    ),
    ChangesetState.REJECTED: frozenset({ChangesetState.DRAFT}),
    ChangesetState.FAILED: frozenset(
        {
            ChangesetState.DRAFT,
            ChangesetState.APPLIED,
            ChangesetState.FAILED,
        }
    ),
    ChangesetState.EXPIRED: frozenset({ChangesetState.DRAFT}),
    ChangesetState.APPLIED: frozenset(),
    ChangesetState.WITHDRAWN: frozenset(),
}
"""Allowed state transitions; states mapping to an empty set are terminal.

REJECTED/FAILED/EXPIRED route back to DRAFT via rework (D20/D21);
FAILED → APPLIED|FAILED is the retry of an already-approved revision (D20).
"""


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return uuid.uuid4().hex


class ChangeItem(BaseModel):
    """One insert/update/delete of a single row in the target table.

    Attributes:
        op: The change operation.
        key: Row identifier (primary-key columns); required for update
            and delete.
        values: Column values; required for insert and update.
    """

    op: ChangeOp
    key: dict[str, object] | None = None
    values: dict[str, object] | None = None


class Changeset(BaseModel):
    """Aggregate root for a proposed configuration change.

    Attributes:
        id: Opaque unique identifier.
        table: The target configuration table.
        maker: User who drafted the changeset.
        title: Short human-readable summary.
        description: Longer rationale for the change.
        items: The row-level changes (editable only in DRAFT).
        state: Current lifecycle state.
        revision: 0 in the initial draft; incremented by each submit (D20).
            Approvals, rejections, and validation reports bind to it.
        review_deadline: Snapshotted on submit from the effective review
            TTL; ``None`` means no expiry (D21).
        apply_deadline: Snapshotted on approve from the effective apply
            TTL; ``None`` means no expiry (D21).
        created_at: Creation timestamp (UTC).
        updated_at: Last transition timestamp (UTC).
    """

    id: str = Field(default_factory=_new_id)
    table: TableRef
    maker: str
    title: str
    description: str = ""
    items: list[ChangeItem] = Field(default_factory=list)
    state: ChangesetState = ChangesetState.DRAFT
    revision: int = 0
    review_deadline: datetime | None = None
    apply_deadline: datetime | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    def transition(self, to_state: ChangesetState) -> None:
        """Move the changeset to a new state.

        Args:
            to_state: The requested next state.

        Raises:
            ChangesetStateError: If the transition is not allowed by
                :data:`ALLOWED_TRANSITIONS`.
        """
        if to_state not in ALLOWED_TRANSITIONS[self.state]:
            raise ChangesetStateError(
                f"Illegal transition {self.state.value!r} -> {to_state.value!r} "
                f"for changeset {self.id}"
            )
        self.state = to_state
        self.updated_at = _utcnow()
