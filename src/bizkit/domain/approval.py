"""Review decisions and approval invariants.

The maker≠checker rule lives here, in the domain — not in the API layer
(spec D8). The only relaxation is the explicit ``allow_self_approval``
flag threaded in from configuration by the service (spec D26/D27); the
domain default stays strict.
"""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from bizkit.domain.changeset import Changeset
from bizkit.exceptions import ApprovalError


class Decision(StrEnum):
    """Outcome of a checker's review."""

    APPROVE = "approve"
    REJECT = "reject"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ReviewDecision(BaseModel):
    """Record of a checker's decision on a submitted changeset.

    Attributes:
        changeset_id: The reviewed changeset.
        revision: The exact revision reviewed (spec D20).
        checker: User who made the decision.
        decision: Approve or reject.
        reason: Free-text justification (mandatory for rejections,
            enforced at the service layer).
        decided_at: Decision timestamp (UTC).
    """

    changeset_id: str
    revision: int
    checker: str
    decision: Decision
    reason: str = ""
    decided_at: datetime = Field(default_factory=_utcnow)


def ensure_checker_is_not_maker(
    changeset: Changeset,
    checker: str,
    allow_self_approval: bool = False,
) -> None:
    """Enforce the four-eyes principle.

    Args:
        changeset: The changeset under review.
        checker: The user attempting to review it.
        allow_self_approval: The effective deployment/table setting
            (spec D26/D27). The domain default is strict.

    Raises:
        ApprovalError: If the checker is the changeset's maker and
            self-approval is not explicitly allowed.
    """
    if checker == changeset.maker and not allow_self_approval:
        raise ApprovalError(
            f"User {checker!r} is the maker of changeset {changeset.id} "
            "and cannot check their own change"
        )
