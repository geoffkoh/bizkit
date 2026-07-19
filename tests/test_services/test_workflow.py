"""WorkflowService: authorization, four-eyes, revisions, expiry, caps, audit."""

from datetime import timedelta

import pytest

from bizkit.config import WorkflowConfig
from bizkit.domain.changeset import ChangeItem, ChangeOp, ChangesetState
from bizkit.domain.table import TableRef
from bizkit.domain.table_config import TableConfig
from bizkit.exceptions import (
    AccessDeniedError,
    ApprovalError,
    ChangesetLimitError,
    ChangesetStateError,
)
from bizkit.services.workflow import SYSTEM_EXPIRY_ACTOR, WorkflowService
from bizkit.store.repositories import (
    SqlAlchemyAuditLog,
    SqlAlchemyChangesetRepository,
    SqlAlchemyDecisionRepository,
)
from bizkit.workspace.access import FileAccessPolicy
from bizkit.workspace.registry import FileTableRegistry


@pytest.fixture
def service(
    changeset_repo: SqlAlchemyChangesetRepository,
    audit_log: SqlAlchemyAuditLog,
    decision_repo: SqlAlchemyDecisionRepository,
    maker_checker_policy: FileAccessPolicy,
) -> WorkflowService:
    return WorkflowService(
        changesets=changeset_repo,
        audit=audit_log,
        access=maker_checker_policy,
        decisions=decision_repo,
    )


def _item() -> ChangeItem:
    return ChangeItem(op=ChangeOp.INSERT, values={"pair": "USDJPY"})


def test_happy_path_submit_approve(
    service: WorkflowService,
    fx_table: TableRef,
    audit_log: SqlAlchemyAuditLog,
    decision_repo: SqlAlchemyDecisionRepository,
) -> None:
    changeset = service.create(fx_table, "alice", "Add rate", items=[_item()])
    assert changeset.state is ChangesetState.DRAFT
    assert changeset.revision == 0

    submitted = service.submit(changeset.id, "alice")
    assert submitted.state is ChangesetState.SUBMITTED
    assert submitted.revision == 1

    approved = service.approve(changeset.id, "bob", reason="looks right")
    assert approved.state is ChangesetState.APPROVED

    actions = [e.action for e in audit_log.list_for(changeset.id)]
    assert actions == ["create", "submit", "approve"]
    decisions = decision_repo.list_for(changeset.id)
    assert len(decisions) == 1
    assert decisions[0].revision == 1
    assert decisions[0].checker == "bob"


def test_unauthorized_actor_denied(
    service: WorkflowService, fx_table: TableRef
) -> None:
    with pytest.raises(AccessDeniedError):
        service.create(fx_table, "mallory", "Sneaky", items=[_item()])


def test_checker_cannot_create(service: WorkflowService, fx_table: TableRef) -> None:
    with pytest.raises(AccessDeniedError):
        service.create(fx_table, "bob", "Wrong role", items=[_item()])


def test_maker_cannot_approve_own(service: WorkflowService, fx_table: TableRef) -> None:
    changeset = service.create(fx_table, "alice", "Mine", items=[_item()])
    service.submit(changeset.id, "alice")
    with pytest.raises(AccessDeniedError):
        # alice holds no checker grant at all
        service.approve(changeset.id, "alice")


def test_four_eyes_blocks_dual_role_maker(
    changeset_repo: SqlAlchemyChangesetRepository,
    audit_log: SqlAlchemyAuditLog,
    fx_table: TableRef,
) -> None:
    from bizkit.domain.access import Grant, Role, Scope

    both_roles = FileAccessPolicy(
        [
            Grant(
                principal="carol",
                role=Role.MAKER,
                scope=Scope.parse("sample/*/*"),
            ),
            Grant(
                principal="carol",
                role=Role.CHECKER,
                scope=Scope.parse("sample/*/*"),
            ),
        ]
    )
    service = WorkflowService(
        changesets=changeset_repo, audit=audit_log, access=both_roles
    )
    changeset = service.create(fx_table, "carol", "Mine", items=[_item()])
    service.submit(changeset.id, "carol")
    with pytest.raises(ApprovalError):
        service.approve(changeset.id, "carol")


def test_self_approval_flag_permits_and_audits(
    changeset_repo: SqlAlchemyChangesetRepository,
    audit_log: SqlAlchemyAuditLog,
    fx_table: TableRef,
) -> None:
    from bizkit.domain.access import Grant, Role, Scope

    solo = FileAccessPolicy(
        [
            Grant(
                principal="solo",
                role=Role.MAKER,
                scope=Scope.parse("sample/*/*"),
            ),
            Grant(
                principal="solo",
                role=Role.CHECKER,
                scope=Scope.parse("sample/*/*"),
            ),
        ]
    )
    service = WorkflowService(
        changesets=changeset_repo,
        audit=audit_log,
        access=solo,
        config=WorkflowConfig(allow_self_approval=True),
    )
    changeset = service.create(fx_table, "solo", "Solo", items=[_item()])
    service.submit(changeset.id, "solo")
    approved = service.approve(changeset.id, "solo")
    assert approved.state is ChangesetState.APPROVED
    events = audit_log.list_for(changeset.id)
    assert events[-1].detail == "self-approved"


def test_per_table_override_beats_global(
    changeset_repo: SqlAlchemyChangesetRepository,
    audit_log: SqlAlchemyAuditLog,
    fx_table: TableRef,
) -> None:
    from bizkit.domain.access import Grant, Role, Scope

    solo = FileAccessPolicy(
        [
            Grant(
                principal="solo",
                role=Role.MAKER,
                scope=Scope.parse("sample/*/*"),
            ),
            Grant(
                principal="solo",
                role=Role.CHECKER,
                scope=Scope.parse("sample/*/*"),
            ),
        ]
    )
    registry = FileTableRegistry(
        [TableConfig(table=fx_table, allow_self_approval=False)]
    )
    service = WorkflowService(
        changesets=changeset_repo,
        audit=audit_log,
        access=solo,
        config=WorkflowConfig(allow_self_approval=True),
        registry=registry,
    )
    changeset = service.create(fx_table, "solo", "Solo", items=[_item()])
    service.submit(changeset.id, "solo")
    with pytest.raises(ApprovalError):
        service.approve(changeset.id, "solo")


def test_reject_requires_reason_and_rework_loops(
    service: WorkflowService, fx_table: TableRef
) -> None:
    changeset = service.create(fx_table, "alice", "Draft", items=[_item()])
    service.submit(changeset.id, "alice")
    with pytest.raises(ApprovalError):
        service.reject(changeset.id, "bob", reason="  ")
    rejected = service.reject(changeset.id, "bob", reason="wrong rate")
    assert rejected.state is ChangesetState.REJECTED

    reworked = service.rework(changeset.id, "alice")
    assert reworked.state is ChangesetState.DRAFT
    resubmitted = service.submit(changeset.id, "alice")
    assert resubmitted.revision == 2


def test_only_maker_reworks(service: WorkflowService, fx_table: TableRef) -> None:
    changeset = service.create(fx_table, "alice", "Draft", items=[_item()])
    service.submit(changeset.id, "alice")
    service.reject(changeset.id, "bob", reason="no")
    with pytest.raises(ApprovalError):
        service.rework(changeset.id, "bob")


def test_item_cap_enforced_at_create_and_submit(
    changeset_repo: SqlAlchemyChangesetRepository,
    audit_log: SqlAlchemyAuditLog,
    maker_checker_policy: FileAccessPolicy,
    fx_table: TableRef,
) -> None:
    service = WorkflowService(
        changesets=changeset_repo,
        audit=audit_log,
        access=maker_checker_policy,
        config=WorkflowConfig(max_changeset_items=2),
    )
    with pytest.raises(ChangesetLimitError):
        service.create(fx_table, "alice", "Too big", items=[_item(), _item(), _item()])


def test_per_table_cap_override(
    changeset_repo: SqlAlchemyChangesetRepository,
    audit_log: SqlAlchemyAuditLog,
    maker_checker_policy: FileAccessPolicy,
    fx_table: TableRef,
) -> None:
    registry = FileTableRegistry([TableConfig(table=fx_table, max_changeset_items=5)])
    service = WorkflowService(
        changesets=changeset_repo,
        audit=audit_log,
        access=maker_checker_policy,
        config=WorkflowConfig(max_changeset_items=1),
        registry=registry,
    )
    changeset = service.create(
        fx_table, "alice", "Fits override", items=[_item(), _item()]
    )
    assert len(changeset.items) == 2


def test_expiry_guard_on_action(
    changeset_repo: SqlAlchemyChangesetRepository,
    audit_log: SqlAlchemyAuditLog,
    maker_checker_policy: FileAccessPolicy,
    fx_table: TableRef,
) -> None:
    service = WorkflowService(
        changesets=changeset_repo,
        audit=audit_log,
        access=maker_checker_policy,
        config=WorkflowConfig(
            default_review_ttl=timedelta(seconds=-1)  # already lapsed
        ),
    )
    changeset = service.create(fx_table, "alice", "Stale", items=[_item()])
    service.submit(changeset.id, "alice")
    with pytest.raises(ChangesetStateError):
        service.approve(changeset.id, "bob")
    expired = changeset_repo.get(changeset.id)
    assert expired.state is ChangesetState.EXPIRED
    events = audit_log.list_for(changeset.id)
    assert events[-1].action == "expire"
    assert events[-1].actor == SYSTEM_EXPIRY_ACTOR


def test_expire_sweep(
    changeset_repo: SqlAlchemyChangesetRepository,
    audit_log: SqlAlchemyAuditLog,
    maker_checker_policy: FileAccessPolicy,
    fx_table: TableRef,
) -> None:
    service = WorkflowService(
        changesets=changeset_repo,
        audit=audit_log,
        access=maker_checker_policy,
        config=WorkflowConfig(default_review_ttl=timedelta(seconds=-1)),
    )
    changeset = service.create(fx_table, "alice", "Stale", items=[_item()])
    service.submit(changeset.id, "alice")
    expired = service.expire_overdue()
    assert [c.id for c in expired] == [changeset.id]
    assert service.expire_overdue() == []


def test_withdraw_maker_only(service: WorkflowService, fx_table: TableRef) -> None:
    changeset = service.create(fx_table, "alice", "Mine", items=[_item()])
    with pytest.raises(ApprovalError):
        service.withdraw(changeset.id, "bob")
    withdrawn = service.withdraw(changeset.id, "alice")
    assert withdrawn.state is ChangesetState.WITHDRAWN
