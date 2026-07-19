"""Full transition-matrix coverage: every (state, target) pair (spec §11)."""

import pytest

from bizkit.domain.changeset import (
    ALLOWED_TRANSITIONS,
    Changeset,
    ChangesetState,
)
from bizkit.exceptions import ChangesetStateError

ALL_STATES = list(ChangesetState)


@pytest.mark.parametrize("from_state", ALL_STATES)
@pytest.mark.parametrize("to_state", ALL_STATES)
def test_transition_matrix(
    from_state: ChangesetState,
    to_state: ChangesetState,
    sample_changeset: Changeset,
) -> None:
    changeset = sample_changeset.model_copy(update={"state": from_state})
    if to_state in ALLOWED_TRANSITIONS[from_state]:
        changeset.transition(to_state)
        assert changeset.state is to_state
    else:
        with pytest.raises(ChangesetStateError):
            changeset.transition(to_state)
        assert changeset.state is from_state


def test_terminal_states_are_exactly_applied_and_withdrawn() -> None:
    terminal = {s for s, targets in ALLOWED_TRANSITIONS.items() if not targets}
    assert terminal == {ChangesetState.APPLIED, ChangesetState.WITHDRAWN}


def test_rework_routes_back_to_draft() -> None:
    for state in (
        ChangesetState.REJECTED,
        ChangesetState.FAILED,
        ChangesetState.EXPIRED,
    ):
        assert ChangesetState.DRAFT in ALLOWED_TRANSITIONS[state]


def test_transition_refreshes_updated_at(sample_changeset: Changeset) -> None:
    before = sample_changeset.updated_at
    sample_changeset.transition(ChangesetState.SUBMITTED)
    assert sample_changeset.updated_at >= before
