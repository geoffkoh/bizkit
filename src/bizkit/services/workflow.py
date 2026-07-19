"""WorkflowService: the ONLY place changeset state transitions happen.

Every operation authorizes through the ``AccessPolicy`` port (spec §3.3),
checks expiry deadlines first (guard-on-action, D21), performs the
transition via the domain, persists with compare-and-set (D31), and
appends exactly one audit event in the same session/transaction (D10).
The caller (unit of work) commits.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Final

from bizkit.config import WorkflowConfig
from bizkit.domain.access import Action
from bizkit.domain.approval import (
    Decision,
    ReviewDecision,
    ensure_checker_is_not_maker,
)
from bizkit.domain.audit import AuditEvent
from bizkit.domain.changeset import ChangeItem, Changeset, ChangesetState
from bizkit.domain.ports import (
    AccessPolicy,
    AuditLog,
    ChangesetRepository,
    DecisionRepository,
    TableRegistry,
)
from bizkit.domain.table import TableRef
from bizkit.exceptions import (
    AccessDeniedError,
    ApprovalError,
    ChangesetLimitError,
)

SYSTEM_EXPIRY_ACTOR: Final[str] = "system:expiry"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class WorkflowService:
    """Maker-checker workflow orchestration.

    Args:
        changesets: Changeset repository (CAS updates, D31).
        audit: Append-only audit log sharing the same session.
        access: Authorization port (file/store/groups adapter, D5/D22).
        config: Workflow policy defaults (TTLs, self-approval, cap).
        registry: Optional table registry for per-table overrides
            (D21/D27/D37); ``None`` falls back to the config defaults.
        decisions: Optional review-decision repository; when provided,
            approve/reject also record a :class:`ReviewDecision`.
    """

    def __init__(
        self,
        changesets: ChangesetRepository,
        audit: AuditLog,
        access: AccessPolicy,
        config: WorkflowConfig | None = None,
        registry: TableRegistry | None = None,
        decisions: DecisionRepository | None = None,
    ) -> None:
        self._changesets = changesets
        self._audit = audit
        self._access = access
        self._config = config or WorkflowConfig()
        self._registry = registry
        self._decisions = decisions

    # -- effective per-table policy (registry override, else defaults) ----

    def _effective_allow_self_approval(self, table: TableRef) -> bool:
        table_config = self._registry.lookup(table) if self._registry else None
        if table_config is not None and table_config.allow_self_approval is not None:
            return table_config.allow_self_approval
        return self._config.allow_self_approval

    def _effective_max_items(self, table: TableRef) -> int:
        table_config = self._registry.lookup(table) if self._registry else None
        if table_config is not None and table_config.max_changeset_items is not None:
            return table_config.max_changeset_items
        return self._config.max_changeset_items

    def _effective_review_deadline(self, table: TableRef) -> datetime | None:
        table_config = self._registry.lookup(table) if self._registry else None
        ttl = (
            table_config.review_ttl
            if table_config is not None and table_config.review_ttl is not None
            else self._config.default_review_ttl
        )
        return _utcnow() + ttl if ttl is not None else None

    def _effective_apply_deadline(self, table: TableRef) -> datetime | None:
        table_config = self._registry.lookup(table) if self._registry else None
        ttl = (
            table_config.apply_ttl
            if table_config is not None and table_config.apply_ttl is not None
            else self._config.default_apply_ttl
        )
        return _utcnow() + ttl if ttl is not None else None

    # -- guards -----------------------------------------------------------

    def _authorize(self, actor: str, action: Action, table: TableRef) -> None:
        if not self._access.is_allowed(actor, action, table):
            raise AccessDeniedError(
                f"User {actor!r} lacks {action.value!r} rights on "
                f"{table.backend}/{table.schema_name or '*'}/{table.table}"
            )

    def _check_item_cap(self, changeset: Changeset) -> None:
        cap = self._effective_max_items(changeset.table)
        if len(changeset.items) > cap:
            raise ChangesetLimitError(
                f"Changeset {changeset.id} has {len(changeset.items)} items, "
                f"exceeding the effective max_changeset_items cap of {cap}"
            )

    def _expire_if_overdue(self, changeset: Changeset) -> Changeset:
        """Materialize expiry before acting on an overdue changeset (D21)."""
        now = _utcnow()
        overdue = (
            changeset.state is ChangesetState.SUBMITTED
            and changeset.review_deadline is not None
            and now > changeset.review_deadline
        ) or (
            changeset.state is ChangesetState.APPROVED
            and changeset.apply_deadline is not None
            and now > changeset.apply_deadline
        )
        if overdue:
            deadline = (
                changeset.review_deadline
                if changeset.state is ChangesetState.SUBMITTED
                else changeset.apply_deadline
            )
            return self._transition(
                changeset,
                ChangesetState.EXPIRED,
                actor=SYSTEM_EXPIRY_ACTOR,
                action="expire",
                detail=f"deadline {deadline} lapsed",
            )
        return changeset

    # -- core transition --------------------------------------------------

    def _transition(
        self,
        changeset: Changeset,
        to_state: ChangesetState,
        actor: str,
        action: str,
        detail: str = "",
    ) -> Changeset:
        from_state = changeset.state
        changeset.transition(to_state)
        self._changesets.update(changeset)
        self._audit.append(
            AuditEvent(
                changeset_id=changeset.id,
                actor=actor,
                action=action,
                from_state=from_state,
                to_state=changeset.state,
                detail=detail,
            )
        )
        return changeset

    # -- operations -------------------------------------------------------

    def create(
        self,
        table: TableRef,
        maker: str,
        title: str,
        description: str = "",
        items: Sequence[ChangeItem] = (),
    ) -> Changeset:
        """Create a DRAFT changeset (requires ``submit`` rights)."""
        self._authorize(maker, Action.SUBMIT, table)
        changeset = Changeset(
            table=table,
            maker=maker,
            title=title,
            description=description,
            items=list(items),
        )
        self._check_item_cap(changeset)
        self._changesets.add(changeset)
        self._audit.append(
            AuditEvent(
                changeset_id=changeset.id,
                actor=maker,
                action="create",
                from_state=None,
                to_state=ChangesetState.DRAFT,
            )
        )
        return changeset

    def submit(self, changeset_id: str, actor: str) -> Changeset:
        """Submit a draft for review; bumps revision, sets review deadline."""
        changeset = self._changesets.get(changeset_id)
        if actor != changeset.maker:
            raise ApprovalError(
                f"Only the maker {changeset.maker!r} may submit changeset "
                f"{changeset.id}, not {actor!r}"
            )
        self._authorize(actor, Action.SUBMIT, changeset.table)
        self._check_item_cap(changeset)
        changeset.revision += 1
        changeset.review_deadline = self._effective_review_deadline(changeset.table)
        return self._transition(
            changeset,
            ChangesetState.SUBMITTED,
            actor=actor,
            action="submit",
            detail=f"revision {changeset.revision}",
        )

    def approve(self, changeset_id: str, checker: str, reason: str = "") -> Changeset:
        """Approve a submitted changeset (four-eyes, D8/D26/D27)."""
        changeset = self._changesets.get(changeset_id)
        changeset = self._expire_if_overdue(changeset)
        self._authorize(checker, Action.APPROVE, changeset.table)
        allow_self = self._effective_allow_self_approval(changeset.table)
        ensure_checker_is_not_maker(changeset, checker, allow_self)
        self_approved = checker == changeset.maker
        detail = "self-approved" if self_approved else reason
        changeset.apply_deadline = self._effective_apply_deadline(changeset.table)
        result = self._transition(
            changeset,
            ChangesetState.APPROVED,
            actor=checker,
            action="approve",
            detail=detail,
        )
        self._record_decision(result, checker, Decision.APPROVE, reason)
        return result

    def reject(self, changeset_id: str, checker: str, reason: str) -> Changeset:
        """Reject a submitted changeset; a reason is mandatory."""
        if not reason.strip():
            raise ApprovalError("Rejection requires a reason")
        changeset = self._changesets.get(changeset_id)
        changeset = self._expire_if_overdue(changeset)
        self._authorize(checker, Action.REJECT, changeset.table)
        ensure_checker_is_not_maker(
            changeset,
            checker,
            self._effective_allow_self_approval(changeset.table),
        )
        result = self._transition(
            changeset,
            ChangesetState.REJECTED,
            actor=checker,
            action="reject",
            detail=reason,
        )
        self._record_decision(result, checker, Decision.REJECT, reason)
        return result

    def rework(self, changeset_id: str, actor: str) -> Changeset:
        """Return a rejected/failed/expired changeset to DRAFT (D20/D21)."""
        changeset = self._changesets.get(changeset_id)
        if actor != changeset.maker:
            raise ApprovalError(
                f"Only the maker {changeset.maker!r} may rework changeset "
                f"{changeset.id}, not {actor!r}"
            )
        return self._transition(
            changeset, ChangesetState.DRAFT, actor=actor, action="rework"
        )

    def withdraw(self, changeset_id: str, actor: str) -> Changeset:
        """Withdraw a draft or submitted changeset (maker only)."""
        changeset = self._changesets.get(changeset_id)
        if actor != changeset.maker:
            raise ApprovalError(
                f"Only the maker {changeset.maker!r} may withdraw changeset "
                f"{changeset.id}, not {actor!r}"
            )
        return self._transition(
            changeset, ChangesetState.WITHDRAWN, actor=actor, action="withdraw"
        )

    def apply(self, changeset_id: str, actor: str) -> Changeset:
        """Apply an approved changeset to its target.

        Raises:
            NotImplementedError: Apply orchestration (pre-apply
                revalidation + backend handoff) lands with the backend
                implementation milestone.
        """
        raise NotImplementedError(
            "Apply orchestration lands with the backend implementation "
            "milestone (see SPECIFICATION.md §13)"
        )

    def expire_overdue(self) -> list[Changeset]:
        """Sweep: expire every overdue changeset (D21).

        Guard-on-action makes this a timeliness optimization, never the
        sole enforcement; concurrent sweeps race benignly (D31).

        Returns:
            The changesets expired by this sweep.
        """
        expired: list[Changeset] = []
        for changeset in self._changesets.list():
            if changeset.state in (
                ChangesetState.SUBMITTED,
                ChangesetState.APPROVED,
            ):
                fresh = self._changesets.get(changeset.id)
                result = self._expire_if_overdue(fresh)
                if result.state is ChangesetState.EXPIRED:
                    expired.append(result)
        return expired

    def _record_decision(
        self,
        changeset: Changeset,
        checker: str,
        decision: Decision,
        reason: str,
    ) -> None:
        if self._decisions is not None:
            self._decisions.add(
                ReviewDecision(
                    changeset_id=changeset.id,
                    revision=changeset.revision,
                    checker=checker,
                    decision=decision,
                    reason=reason,
                )
            )
