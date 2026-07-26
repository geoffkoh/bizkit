"""WorkflowService.apply: authorization, pre-apply revalidation, APPLIED/FAILED.

Apply is the only path that writes to a target (spec §5), so the guards
matter more here than anywhere else: the actor needs `apply` rights, the
deadline is checked first, validation runs *again* because the target may
have drifted since approval (D12), and every outcome — success or failure —
leaves exactly one audit event describing it.
"""

from datetime import timedelta

import pytest

from bizkit.config import WorkflowConfig
from bizkit.domain.changeset import ChangeItem, ChangeOp, Changeset, ChangesetState
from bizkit.domain.table import ColumnSpec, TableRef
from bizkit.domain.table_config import TableConfig
from bizkit.domain.validation import ConstraintRule
from bizkit.exceptions import AccessDeniedError, ApplyError, ChangesetStateError
from bizkit.services.workflow import WorkflowService
from bizkit.store.repositories import (
    SqlAlchemyAuditLog,
    SqlAlchemyChangesetRepository,
    SqlAlchemyDecisionRepository,
)
from bizkit.workspace.access import FileAccessPolicy
from bizkit.workspace.registry import FileTableRegistry


class FakeBackend:
    """Records what apply/dry_run were asked to do; optionally fails."""

    name = "sample"

    def __init__(self, fail_with: str | None = None) -> None:
        self.fail_with = fail_with
        self.applied: list[Changeset] = []
        self.rehearsed: list[Changeset] = []
        self.rows: list[dict[str, object]] = []

    def introspect_table(self, ref: TableRef) -> list[ColumnSpec]:
        return [ColumnSpec(name="pair", type="string", primary_key=True)]

    def read_rows(self, ref: TableRef, columns: object) -> list[dict[str, object]]:
        return self.rows

    def dry_run(self, changeset: Changeset) -> None:
        self.rehearsed.append(changeset)
        if self.fail_with:
            raise ApplyError(self.fail_with)

    def apply(self, changeset: Changeset) -> None:
        if self.fail_with:
            raise ApplyError(self.fail_with)
        self.applied.append(changeset)


def make_service(
    changeset_repo: SqlAlchemyChangesetRepository,
    audit_log: SqlAlchemyAuditLog,
    decision_repo: SqlAlchemyDecisionRepository,
    access: FileAccessPolicy,
    backend: FakeBackend,
    registry: FileTableRegistry | None = None,
    config: WorkflowConfig | None = None,
) -> WorkflowService:
    return WorkflowService(
        changesets=changeset_repo,
        audit=audit_log,
        access=access,
        config=config,
        registry=registry,
        decisions=decision_repo,
        backend_for=lambda _ref: backend,
    )


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend()


@pytest.fixture
def service(
    changeset_repo: SqlAlchemyChangesetRepository,
    audit_log: SqlAlchemyAuditLog,
    decision_repo: SqlAlchemyDecisionRepository,
    maker_checker_policy: FileAccessPolicy,
    backend: FakeBackend,
) -> WorkflowService:
    return make_service(
        changeset_repo, audit_log, decision_repo, maker_checker_policy, backend
    )


def _item() -> ChangeItem:
    return ChangeItem(op=ChangeOp.INSERT, values={"pair": "USDJPY"})


def approved_changeset(service: WorkflowService, fx_table: TableRef) -> Changeset:
    changeset = service.create(fx_table, "alice", "Add rate", items=[_item()])
    service.submit(changeset.id, "alice")
    return service.approve(changeset.id, "bob")


def test_applies_an_approved_changeset(
    service: WorkflowService,
    fx_table: TableRef,
    backend: FakeBackend,
    audit_log: SqlAlchemyAuditLog,
) -> None:
    changeset = approved_changeset(service, fx_table)

    result = service.apply(changeset.id, "bob")

    assert result.changeset.state is ChangesetState.APPLIED
    assert result.ok is True
    assert len(backend.applied) == 1
    actions = [e.action for e in audit_log.list_for(changeset.id)]
    assert actions == ["create", "submit", "approve", "apply"]


def test_requires_apply_rights(
    service: WorkflowService, fx_table: TableRef, backend: FakeBackend
) -> None:
    # alice is a maker; Action.APPLY belongs to the checker role.
    changeset = approved_changeset(service, fx_table)
    with pytest.raises(AccessDeniedError):
        service.apply(changeset.id, "alice")
    assert backend.applied == []


def test_refuses_a_changeset_that_was_never_approved(
    service: WorkflowService, fx_table: TableRef, backend: FakeBackend
) -> None:
    changeset = service.create(fx_table, "alice", "Add rate", items=[_item()])
    with pytest.raises(ChangesetStateError):
        service.apply(changeset.id, "bob")
    assert backend.applied == []


def test_refuses_a_submitted_changeset(
    service: WorkflowService, fx_table: TableRef, backend: FakeBackend
) -> None:
    changeset = service.create(fx_table, "alice", "Add rate", items=[_item()])
    service.submit(changeset.id, "alice")
    with pytest.raises(ChangesetStateError):
        service.apply(changeset.id, "bob")
    assert backend.applied == []


def test_an_overdue_approval_expires_instead_of_applying(
    changeset_repo: SqlAlchemyChangesetRepository,
    audit_log: SqlAlchemyAuditLog,
    decision_repo: SqlAlchemyDecisionRepository,
    maker_checker_policy: FileAccessPolicy,
    backend: FakeBackend,
    fx_table: TableRef,
) -> None:
    # Guard-on-action (D21): a lapsed apply window is materialized first.
    registry = FileTableRegistry(
        [TableConfig(table=fx_table, apply_ttl=timedelta(seconds=-1))]
    )
    service = make_service(
        changeset_repo,
        audit_log,
        decision_repo,
        maker_checker_policy,
        backend,
        registry=registry,
    )
    changeset = approved_changeset(service, fx_table)

    with pytest.raises(ChangesetStateError):
        service.apply(changeset.id, "bob")

    assert changeset_repo.get(changeset.id).state is ChangesetState.EXPIRED
    assert backend.applied == []


def test_revalidates_before_applying_and_fails_closed(
    changeset_repo: SqlAlchemyChangesetRepository,
    audit_log: SqlAlchemyAuditLog,
    decision_repo: SqlAlchemyDecisionRepository,
    maker_checker_policy: FileAccessPolicy,
    backend: FakeBackend,
    fx_table: TableRef,
) -> None:
    # The changeset passes validation at submit, then the world moves: by
    # apply time the rule set forbids what it carries. That gap is precisely
    # why D12 revalidates instead of trusting the submit-time report.
    lenient = make_service(
        changeset_repo, audit_log, decision_repo, maker_checker_policy, backend
    )
    changeset = approved_changeset(lenient, fx_table)

    registry = FileTableRegistry(
        [
            TableConfig(
                table=fx_table,
                rules=[
                    ConstraintRule(
                        rule_id="pair-known",
                        column="pair",
                        allowed_values=["EURUSD"],
                    )
                ],
            )
        ]
    )
    strict = make_service(
        changeset_repo,
        audit_log,
        decision_repo,
        maker_checker_policy,
        backend,
        registry=registry,
    )

    result = strict.apply(changeset.id, "bob")

    assert result.ok is False
    assert result.changeset.state is ChangesetState.FAILED
    assert result.report is not None and result.report.ok is False
    assert backend.applied == []
    last = audit_log.list_for(changeset.id)[-1]
    assert last.action == "apply_failed"
    assert "validation" in last.detail.lower()


def test_a_target_error_lands_in_failed_with_the_reason_audited(
    changeset_repo: SqlAlchemyChangesetRepository,
    audit_log: SqlAlchemyAuditLog,
    decision_repo: SqlAlchemyDecisionRepository,
    maker_checker_policy: FileAccessPolicy,
    fx_table: TableRef,
) -> None:
    backend = FakeBackend(fail_with="unique constraint violated")
    service = make_service(
        changeset_repo, audit_log, decision_repo, maker_checker_policy, backend
    )
    changeset = approved_changeset(service, fx_table)

    result = service.apply(changeset.id, "bob")

    assert result.ok is False
    assert result.changeset.state is ChangesetState.FAILED
    assert result.error is not None
    assert "unique constraint" in result.error
    last = audit_log.list_for(changeset.id)[-1]
    assert last.action == "apply_failed"
    assert "unique constraint" in last.detail


def test_a_failed_changeset_can_be_retried(
    changeset_repo: SqlAlchemyChangesetRepository,
    audit_log: SqlAlchemyAuditLog,
    decision_repo: SqlAlchemyDecisionRepository,
    maker_checker_policy: FileAccessPolicy,
    fx_table: TableRef,
) -> None:
    # FAILED -> APPLIED without a fresh approval (D20): same approved revision.
    backend = FakeBackend(fail_with="transient outage")
    service = make_service(
        changeset_repo, audit_log, decision_repo, maker_checker_policy, backend
    )
    changeset = approved_changeset(service, fx_table)
    assert service.apply(changeset.id, "bob").changeset.state is ChangesetState.FAILED

    backend.fail_with = None
    result = service.apply(changeset.id, "bob")

    assert result.changeset.state is ChangesetState.APPLIED
    assert len(backend.applied) == 1


def test_applied_is_terminal(service: WorkflowService, fx_table: TableRef) -> None:
    changeset = approved_changeset(service, fx_table)
    service.apply(changeset.id, "bob")
    with pytest.raises(ChangesetStateError):
        service.apply(changeset.id, "bob")


def test_exactly_one_audit_event_per_apply_attempt(
    changeset_repo: SqlAlchemyChangesetRepository,
    audit_log: SqlAlchemyAuditLog,
    decision_repo: SqlAlchemyDecisionRepository,
    maker_checker_policy: FileAccessPolicy,
    fx_table: TableRef,
) -> None:
    backend = FakeBackend(fail_with="boom")
    service = make_service(
        changeset_repo, audit_log, decision_repo, maker_checker_policy, backend
    )
    changeset = approved_changeset(service, fx_table)
    before = len(audit_log.list_for(changeset.id))

    service.apply(changeset.id, "bob")

    assert len(audit_log.list_for(changeset.id)) == before + 1


def test_cross_table_rules_receive_the_target_backend(
    changeset_repo: SqlAlchemyChangesetRepository,
    audit_log: SqlAlchemyAuditLog,
    decision_repo: SqlAlchemyDecisionRepository,
    maker_checker_policy: FileAccessPolicy,
    fx_table: TableRef,
) -> None:
    # Without the backend a cross-table rule reports instead of passing, so
    # this asserts the wiring rather than the rule.
    from bizkit.domain.validation import CrossTableRule

    backend = FakeBackend()
    backend.rows = [{"name": "USDJPY"}]
    registry = FileTableRegistry(
        [
            TableConfig(
                table=fx_table,
                rules=[
                    CrossTableRule(
                        rule_id="pair-listed",
                        ref_table=TableRef(backend="sample", table="listed_pairs"),
                        local_columns=["pair"],
                        ref_columns=["name"],
                    )
                ],
            )
        ]
    )
    service = make_service(
        changeset_repo,
        audit_log,
        decision_repo,
        maker_checker_policy,
        backend,
        registry=registry,
    )
    changeset = approved_changeset(service, fx_table)

    result = service.apply(changeset.id, "bob")

    assert result.ok is True
    assert result.changeset.state is ChangesetState.APPLIED


def test_without_a_backend_apply_refuses_rather_than_pretending(
    changeset_repo: SqlAlchemyChangesetRepository,
    audit_log: SqlAlchemyAuditLog,
    decision_repo: SqlAlchemyDecisionRepository,
    maker_checker_policy: FileAccessPolicy,
    fx_table: TableRef,
) -> None:
    service = WorkflowService(
        changesets=changeset_repo,
        audit=audit_log,
        access=maker_checker_policy,
        decisions=decision_repo,
    )
    changeset = approved_changeset(service, fx_table)
    with pytest.raises(ApplyError, match="no target backend"):
        service.apply(changeset.id, "bob")
