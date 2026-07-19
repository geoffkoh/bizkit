"""Four-eyes rule: strict default and the D26/D27 relaxation."""

import pytest

from bizkit.domain.approval import ensure_checker_is_not_maker
from bizkit.domain.changeset import Changeset
from bizkit.exceptions import ApprovalError


def test_maker_cannot_check_own_change(sample_changeset: Changeset) -> None:
    with pytest.raises(ApprovalError):
        ensure_checker_is_not_maker(sample_changeset, "alice")


def test_distinct_checker_is_fine(sample_changeset: Changeset) -> None:
    ensure_checker_is_not_maker(sample_changeset, "bob")


def test_self_approval_requires_explicit_flag(
    sample_changeset: Changeset,
) -> None:
    ensure_checker_is_not_maker(sample_changeset, "alice", allow_self_approval=True)


def test_flag_does_not_affect_distinct_checkers(
    sample_changeset: Changeset,
) -> None:
    ensure_checker_is_not_maker(sample_changeset, "bob", allow_self_approval=True)
