"""Validation at submit (spec D12, the first of the two mandated runs).

Submit-time validation keeps invalid work out of a checker's queue. It is
deliberately *not* a substitute for the pre-apply run — see
`test_workflow_apply.py` for the drift case that only revalidation catches.
"""

import pytest

from bizkit.domain.changeset import ChangeItem, ChangeOp, ChangesetState
from bizkit.domain.table import TableRef
from bizkit.domain.table_config import TableConfig
from bizkit.domain.validation import (
    ConstraintRule,
    CrossFieldRule,
    CrossTableRule,
    TypeRule,
    ValidationReport,
)
from bizkit.exceptions import ValidationFailedError
from bizkit.services.workflow import WorkflowService
from bizkit.store.repositories import (
    SqlAlchemyAuditLog,
    SqlAlchemyChangesetRepository,
    SqlAlchemyDecisionRepository,
)
from bizkit.workspace.access import FileAccessPolicy
from bizkit.workspace.registry import FileTableRegistry


@pytest.fixture
def rules_registry(fx_table: TableRef) -> FileTableRegistry:
    return FileTableRegistry(
        [
            TableConfig(
                table=fx_table,
                rules=[
                    ConstraintRule(
                        rule_id="rate-positive",
                        column="rate",
                        min_value=0,
                        not_null=True,
                    ),
                    TypeRule(
                        rule_id="rate-numeric", column="rate", expected_type="decimal"
                    ),
                    CrossFieldRule(
                        rule_id="pair-format",
                        columns=["pair"],
                        predicate="pair-is-6-uppercase",
                    ),
                ],
            )
        ]
    )


@pytest.fixture
def service(
    changeset_repo: SqlAlchemyChangesetRepository,
    audit_log: SqlAlchemyAuditLog,
    decision_repo: SqlAlchemyDecisionRepository,
    maker_checker_policy: FileAccessPolicy,
    rules_registry: FileTableRegistry,
) -> WorkflowService:
    return WorkflowService(
        changesets=changeset_repo,
        audit=audit_log,
        access=maker_checker_policy,
        registry=rules_registry,
        decisions=decision_repo,
    )


def test_a_valid_changeset_submits(
    service: WorkflowService, fx_table: TableRef
) -> None:
    changeset = service.create(
        fx_table,
        "alice",
        "Add rate",
        items=[
            ChangeItem(op=ChangeOp.INSERT, values={"pair": "USDJPY", "rate": 155.2})
        ],
    )
    assert service.submit(changeset.id, "alice").state is ChangesetState.SUBMITTED


def test_a_blocking_issue_prevents_submit(
    service: WorkflowService,
    fx_table: TableRef,
    changeset_repo: SqlAlchemyChangesetRepository,
) -> None:
    changeset = service.create(
        fx_table,
        "alice",
        "Bad rate",
        items=[ChangeItem(op=ChangeOp.INSERT, values={"pair": "USDJPY", "rate": -1})],
    )
    with pytest.raises(ValidationFailedError) as caught:
        service.submit(changeset.id, "alice")

    # Still a draft, revision untouched: a failed submit is not a transition.
    stored = changeset_repo.get(changeset.id)
    assert stored.state is ChangesetState.DRAFT
    assert stored.revision == 0
    report = caught.value.report
    assert isinstance(report, ValidationReport)
    assert [i.rule_id for i in report.issues] == ["rate-positive"]


def test_the_error_carries_the_structured_report(
    service: WorkflowService, fx_table: TableRef
) -> None:
    changeset = service.create(
        fx_table,
        "alice",
        "Two problems",
        items=[ChangeItem(op=ChangeOp.INSERT, values={"pair": "usd", "rate": "abc"})],
    )
    with pytest.raises(ValidationFailedError) as caught:
        service.submit(changeset.id, "alice")

    report = caught.value.report
    assert isinstance(report, ValidationReport)
    assert {i.rule_id for i in report.issues} == {
        "rate-numeric",
        "pair-format",
        "rate-positive",
    }


def test_no_rule_set_means_nothing_to_block(
    changeset_repo: SqlAlchemyChangesetRepository,
    audit_log: SqlAlchemyAuditLog,
    maker_checker_policy: FileAccessPolicy,
    fx_table: TableRef,
) -> None:
    service = WorkflowService(
        changesets=changeset_repo, audit=audit_log, access=maker_checker_policy
    )
    changeset = service.create(
        fx_table,
        "alice",
        "Anything",
        items=[ChangeItem(op=ChangeOp.INSERT, values={"whatever": -1})],
    )
    assert service.submit(changeset.id, "alice").state is ChangesetState.SUBMITTED


def test_a_cross_table_rule_without_a_backend_blocks_rather_than_passes(
    changeset_repo: SqlAlchemyChangesetRepository,
    audit_log: SqlAlchemyAuditLog,
    maker_checker_policy: FileAccessPolicy,
    fx_table: TableRef,
) -> None:
    # Failing open here would let an unvalidated row reach a checker.
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
    service = WorkflowService(
        changesets=changeset_repo,
        audit=audit_log,
        access=maker_checker_policy,
        registry=registry,
    )
    changeset = service.create(
        fx_table,
        "alice",
        "Add rate",
        items=[ChangeItem(op=ChangeOp.INSERT, values={"pair": "USDJPY"})],
    )
    with pytest.raises(ValidationFailedError, match="no target connection"):
        service.submit(changeset.id, "alice")


def test_validate_can_be_called_without_transitioning(
    service: WorkflowService, fx_table: TableRef
) -> None:
    changeset = service.create(
        fx_table,
        "alice",
        "Bad rate",
        items=[ChangeItem(op=ChangeOp.INSERT, values={"pair": "USDJPY", "rate": -1})],
    )
    report = service.validate(changeset)
    assert report.ok is False
    assert changeset.state is ChangesetState.DRAFT
