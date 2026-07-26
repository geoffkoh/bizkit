"""WorkflowService: the ONLY place changeset state transitions happen.

Every operation authorizes through the ``AccessPolicy`` port (spec §3.3),
checks expiry deadlines first (guard-on-action, D21), performs the
transition via the domain, persists with compare-and-set (D31), and
appends exactly one audit event in the same session/transaction (D10).
The caller (unit of work) commits.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
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
    TargetBackend,
)
from bizkit.domain.table import TableRef
from bizkit.domain.validation import BaseRule, Severity, ValidationReport
from bizkit.exceptions import (
    AccessDeniedError,
    ApplyError,
    ApprovalError,
    ChangesetLimitError,
    ValidationFailedError,
)
from bizkit.services.validation import RowsFor, ValidationService

SYSTEM_EXPIRY_ACTOR: Final[str] = "system:expiry"


@dataclass(frozen=True)
class ApplyResult:
    """Outcome of an apply attempt.

    A target-side failure is a *result*, not an exception: the changeset
    moves to FAILED and that transition must be committed along with its
    audit event, so the caller needs it back rather than an unwound
    transaction. Pre-conditions that change nothing (no rights, wrong
    state, lapsed deadline) still raise.

    Attributes:
        changeset: The changeset in its post-attempt state.
        report: The pre-apply validation report when validation blocked the
            attempt, else ``None``.
        error: The target's complaint when the write itself failed, else
            ``None``.
    """

    changeset: Changeset
    report: ValidationReport | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        """Whether the changeset reached APPLIED."""
        return self.changeset.state is ChangesetState.APPLIED


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
        backend_for: Resolves a table to its target backend. Required for
            :meth:`apply`, which otherwise has nothing to write to.
        validation: Rule runner; a default instance is used when omitted.
    """

    def __init__(
        self,
        changesets: ChangesetRepository,
        audit: AuditLog,
        access: AccessPolicy,
        config: WorkflowConfig | None = None,
        registry: TableRegistry | None = None,
        decisions: DecisionRepository | None = None,
        backend_for: Callable[[TableRef], TargetBackend] | None = None,
        validation: ValidationService | None = None,
    ) -> None:
        self._changesets = changesets
        self._audit = audit
        self._access = access
        self._config = config or WorkflowConfig()
        self._registry = registry
        self._decisions = decisions
        self._backend_for = backend_for
        self._validation = validation or ValidationService()

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
        # Validation runs at submit AND again pre-apply (D12). This one keeps
        # invalid work out of a checker's queue; the pre-apply run is what
        # catches target drift between approval and apply.
        report = self.validate(changeset)
        if not report.ok:
            blocking = [i for i in report.issues if i.severity is Severity.ERROR]
            raise ValidationFailedError(
                f"Changeset {changeset.id} failed validation with "
                f"{len(blocking)} blocking issue(s): {blocking[0].message}",
                report=report,
            )
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

    def _rows_for(self) -> RowsFor | None:
        """A lazy, per-table row fetch for cross-table rules.

        Resolution happens inside the callback, so a rule set with no
        cross-table rules never touches a target — and one that *does* may
        reference a table in a different backend than the changeset's.
        """
        if self._backend_for is None:
            return None
        backend_for = self._backend_for

        def rows_for(ref: TableRef, columns: Sequence[str]) -> list[dict[str, object]]:
            return backend_for(ref).read_rows(ref, columns)

        return rows_for

    def _rules_for(self, table: TableRef) -> Sequence[BaseRule]:
        table_config = self._registry.lookup(table) if self._registry else None
        return table_config.rules if table_config is not None else ()

    def validate(
        self, changeset: Changeset, rows_for: RowsFor | None = None
    ) -> ValidationReport:
        """Run the table's rule set against a changeset (D12).

        Args:
            changeset: The changeset to validate.
            rows_for: Row fetch for cross-table rules; defaults to the
                service's own resolver. Without either, those rules report
                rather than pass.

        Returns:
            The structured report.
        """
        return self._validation.validate(
            changeset,
            self._rules_for(changeset.table),
            rows_for if rows_for is not None else self._rows_for(),
        )

    def apply(self, changeset_id: str, actor: str) -> ApplyResult:
        """Apply an approved changeset to its target database.

        The only workflow operation that reaches a target. In order: expiry
        guard, `apply` authorization, revalidation against the *current*
        target (D12 — approval may be hours old and the target may have
        drifted), then the backend handoff. Success transitions to APPLIED;
        a validation or target failure transitions to FAILED, from which the
        maker can rework or the checker can retry (D20).

        Args:
            changeset_id: The changeset to apply.
            actor: The principal applying it; needs `apply` rights, which
                the default role mapping grants to checkers.

        Returns:
            An :class:`ApplyResult` carrying the post-attempt changeset and,
            when the attempt failed, the reason.

        Raises:
            AccessDeniedError: The actor lacks `apply` rights.
            ChangesetStateError: The changeset is not in an applicable
                state (including one just expired by the deadline guard).
            ApplyError: No backend is configured to write to.
        """
        changeset = self._changesets.get(changeset_id)
        changeset = self._expire_if_overdue(changeset)
        self._authorize(actor, Action.APPLY, changeset.table)

        # Fail before touching the target if the state forbids applying at
        # all, so a doomed attempt never opens a target transaction.
        if changeset.state not in (ChangesetState.APPROVED, ChangesetState.FAILED):
            changeset.transition(ChangesetState.APPLIED)  # raises, by design

        if self._backend_for is None:
            raise ApplyError(
                f"Cannot apply changeset {changeset.id}: no target backend is "
                "configured for this service"
            )
        backend = self._backend_for(changeset.table)

        report = self.validate(changeset)
        if not report.ok:
            blocking = [i for i in report.issues if i.severity.value == "error"]
            detail = (
                f"pre-apply validation failed with {len(blocking)} blocking "
                f"issue(s): {blocking[0].message}"
                if blocking
                else "pre-apply validation failed"
            )
            failed = self._transition(
                changeset,
                ChangesetState.FAILED,
                actor=actor,
                action="apply_failed",
                detail=detail,
            )
            return ApplyResult(changeset=failed, report=report)

        try:
            backend.apply(changeset)
        except (ApplyError, ValidationFailedError) as exc:
            failed = self._transition(
                changeset,
                ChangesetState.FAILED,
                actor=actor,
                action="apply_failed",
                detail=str(exc),
            )
            return ApplyResult(changeset=failed, error=str(exc))

        applied = self._transition(
            changeset,
            ChangesetState.APPLIED,
            actor=actor,
            action="apply",
            detail=f"revision {changeset.revision}, {len(changeset.items)} item(s)",
        )
        return ApplyResult(changeset=applied)

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
