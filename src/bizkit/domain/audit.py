"""Immutable audit events.

Every state transition writes exactly one :class:`AuditEvent`, in the same
store transaction as the transition itself. Events are frozen: an audit
trail is append-only.
"""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from bizkit.domain.changeset import ChangesetState


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return uuid.uuid4().hex


class AuditEvent(BaseModel):
    """Immutable record of an action on a changeset.

    Attributes:
        id: Opaque unique identifier.
        changeset_id: The changeset acted upon.
        actor: User who performed the action.
        action: Verb describing the action (``create``, ``submit``,
            ``approve``, ``reject``, ``withdraw``, ``apply``, ``comment``).
        from_state: State before the action, if it was a transition.
        to_state: State after the action, if it was a transition.
        detail: Optional free-text detail (e.g. rejection reason).
        at: Event timestamp (UTC).
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=_new_id)
    changeset_id: str
    actor: str
    action: str
    from_state: ChangesetState | None = None
    to_state: ChangesetState | None = None
    detail: str = ""
    at: datetime = Field(default_factory=_utcnow)
