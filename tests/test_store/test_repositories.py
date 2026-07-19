"""Store round-trips and the optimistic-lock CAS contract (spec D31)."""

import pytest

from bizkit.domain.audit import AuditEvent
from bizkit.domain.changeset import Changeset, ChangesetState
from bizkit.exceptions import ConcurrencyError, StoreError
from bizkit.store.repositories import (
    SqlAlchemyAuditLog,
    SqlAlchemyChangesetRepository,
)
from sqlalchemy.orm import Session


def test_changeset_roundtrip(
    changeset_repo: SqlAlchemyChangesetRepository,
    sample_changeset: Changeset,
) -> None:
    changeset_repo.add(sample_changeset)
    loaded = changeset_repo.get(sample_changeset.id)
    assert loaded == sample_changeset


def test_get_missing_raises(
    changeset_repo: SqlAlchemyChangesetRepository,
) -> None:
    with pytest.raises(StoreError):
        changeset_repo.get("nope")


def test_update_persists_state(
    changeset_repo: SqlAlchemyChangesetRepository,
    sample_changeset: Changeset,
) -> None:
    changeset_repo.add(sample_changeset)
    loaded = changeset_repo.get(sample_changeset.id)
    loaded.transition(ChangesetState.SUBMITTED)
    changeset_repo.update(loaded)
    again = changeset_repo.get(sample_changeset.id)
    assert again.state is ChangesetState.SUBMITTED


def test_concurrent_update_loses_cleanly(
    store_session: Session,
    sample_changeset: Changeset,
) -> None:
    repo_one = SqlAlchemyChangesetRepository(store_session)
    repo_two = SqlAlchemyChangesetRepository(store_session)
    repo_one.add(sample_changeset)

    first = repo_one.get(sample_changeset.id)
    second = repo_two.get(sample_changeset.id)

    first.transition(ChangesetState.SUBMITTED)
    repo_one.update(first)

    second.transition(ChangesetState.WITHDRAWN)
    with pytest.raises(ConcurrencyError):
        repo_two.update(second)

    assert repo_one.get(sample_changeset.id).state is ChangesetState.SUBMITTED


def test_update_requires_prior_get(
    changeset_repo: SqlAlchemyChangesetRepository,
    sample_changeset: Changeset,
) -> None:
    with pytest.raises(StoreError):
        changeset_repo.update(sample_changeset)


def test_audit_append_order(
    audit_log: SqlAlchemyAuditLog,
) -> None:
    for n in range(3):
        audit_log.append(AuditEvent(changeset_id="cs1", actor="alice", action=f"a{n}"))
    actions = [e.action for e in audit_log.list_for("cs1")]
    assert actions == ["a0", "a1", "a2"]
