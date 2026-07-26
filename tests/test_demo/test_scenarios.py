"""Demo scenarios (spec D45).

The load-bearing test here is `test_every_approved_changeset_can_actually_apply`:
before apply existed (D44), a scenario could seed an APPROVED changeset that
was impossible to apply — the target already held the row it inserts — and
nothing caught it. That is now a property every scenario must satisfy, so a
future scenario cannot reintroduce it.
"""

import sqlite3
from collections.abc import Sequence
from pathlib import Path

import pytest

from bizkit.backends.registry import get_backend_class
from bizkit.demo import SCENARIOS, seed
from bizkit.demo.model import Scenario
from bizkit.domain.changeset import Changeset, ChangesetState
from bizkit.domain.table import TableRef
from bizkit.store.engine import create_session_factory, create_store_engine
from bizkit.store.repositories import SqlAlchemyChangesetRepository
from bizkit.workspace.loader import load_workspace

SCENARIO_NAMES = sorted(SCENARIOS)


@pytest.fixture
def seeded(
    tmp_path: Path, request: pytest.FixtureRequest
) -> tuple[Scenario, Path, str]:
    """Seed the requested scenario into a temp directory."""
    name: str = request.param
    store_url = f"sqlite:///{tmp_path / 'store.db'}"
    scenario = SCENARIOS[name]
    seed(scenario, store_url=store_url, workspace_path=tmp_path / "ws.json")
    return scenario, tmp_path, store_url


def _changesets(store_url: str) -> list[Changeset]:
    engine = create_store_engine(store_url)
    with create_session_factory(engine)() as session:
        return SqlAlchemyChangesetRepository(session).list()


@pytest.mark.parametrize("seeded", SCENARIO_NAMES, indirect=True)
def test_scenario_writes_its_workspace_and_targets(
    seeded: tuple[Scenario, Path, str],
) -> None:
    scenario, directory, _ = seeded
    assert (directory / "ws.json").exists()
    for profile in scenario.targets:
        assert (directory / f"{profile}_target.db").exists()
    # The workspace it wrote must load cleanly under the D23 schema.
    loaded = load_workspace(directory / "ws.json")
    assert set(loaded.config.targets) == set(scenario.targets)
    assert loaded.tables and loaded.grants


@pytest.mark.parametrize("seeded", SCENARIO_NAMES, indirect=True)
def test_scenario_seeds_a_usable_history(seeded: tuple[Scenario, Path, str]) -> None:
    _, _, store_url = seeded
    changesets = _changesets(store_url)
    assert len(changesets) >= 8
    states = {c.state for c in changesets}
    # A demo is only useful if a reviewer has something to review and a
    # reader something to read.
    assert ChangesetState.DRAFT in states
    assert ChangesetState.SUBMITTED in states


@pytest.mark.parametrize("seeded", SCENARIO_NAMES, indirect=True)
def test_every_approved_changeset_can_actually_apply(
    seeded: tuple[Scenario, Path, str],
) -> None:
    """An APPROVED changeset a checker cannot apply is a broken demo.

    Uses dry_run, so the targets are left exactly as the scenario built them.
    """
    _, directory, store_url = seeded
    loaded = load_workspace(directory / "ws.json")
    approved = [c for c in _changesets(store_url) if c.state is ChangesetState.APPROVED]
    assert approved, "a scenario should leave something for a checker to apply"
    for changeset in approved:
        target = loaded.config.targets[changeset.table.backend]
        backend = get_backend_class(target.backend)(target.url)
        # Raises ApplyError if the target could not accept it.
        backend.dry_run(changeset)


@pytest.mark.parametrize("seeded", SCENARIO_NAMES, indirect=True)
def test_pending_updates_and_deletes_target_rows_that_exist(
    seeded: tuple[Scenario, Path, str],
) -> None:
    """The mirror of the above for the not-yet-approved changesets.

    An update or delete keyed to a row that is not there would fail at apply
    time, which is far too late to discover a fixture mistake.
    """
    _, directory, store_url = seeded
    loaded = load_workspace(directory / "ws.json")
    pending = (ChangesetState.DRAFT, ChangesetState.SUBMITTED, ChangesetState.APPROVED)
    for changeset in _changesets(store_url):
        if changeset.state not in pending:
            continue
        db = directory / f"{changeset.table.backend}_target.db"
        assert db.exists()
        with sqlite3.connect(db) as conn:
            for item in changeset.items:
                if not item.key:
                    continue
                where = " AND ".join(f'"{c}" = ?' for c in item.key)
                found = conn.execute(
                    f'SELECT count(*) FROM "{changeset.table.table}" WHERE {where}',  # noqa: S608
                    tuple(item.key.values()),
                ).fetchone()[0]
                assert found == 1, (
                    f"{changeset.title!r} targets {item.key} in "
                    f"{changeset.table.table}, which is not in the seeded target"
                )
        assert loaded.config.targets[changeset.table.backend]


class TestSampleScenario:
    def test_shape(self, tmp_path: Path) -> None:
        store_url = f"sqlite:///{tmp_path / 'store.db'}"
        seed(
            SCENARIOS["sample"],
            store_url=store_url,
            workspace_path=tmp_path / "ws.json",
        )
        changesets = _changesets(store_url)
        assert len(changesets) == 8
        census = {c.state for c in changesets}
        assert census == {
            ChangesetState.DRAFT,
            ChangesetState.SUBMITTED,
            ChangesetState.APPROVED,
            ChangesetState.REJECTED,
            ChangesetState.WITHDRAWN,
            ChangesetState.EXPIRED,
        }
        # sample deliberately stops short of the target.
        assert ChangesetState.APPLIED not in census
        assert ChangesetState.FAILED not in census


class TestEnterpriseScenario:
    @pytest.fixture
    def run(self, tmp_path: Path) -> tuple[Path, str]:
        store_url = f"sqlite:///{tmp_path / 'store.db'}"
        seed(
            SCENARIOS["enterprise"],
            store_url=store_url,
            workspace_path=tmp_path / "ws.json",
        )
        return tmp_path, store_url

    def test_covers_every_state_including_applied_and_failed(
        self, run: tuple[Path, str]
    ) -> None:
        _, store_url = run
        changesets = _changesets(store_url)
        assert len(changesets) == 10
        census = {c.state for c in changesets}
        assert census == {
            ChangesetState.DRAFT,
            ChangesetState.SUBMITTED,
            ChangesetState.APPROVED,
            ChangesetState.APPLIED,
            ChangesetState.FAILED,
            ChangesetState.WITHDRAWN,
            ChangesetState.EXPIRED,
        }

    def test_the_applied_changeset_really_wrote_its_row(
        self, run: tuple[Path, str]
    ) -> None:
        directory, _ = run
        with sqlite3.connect(directory / "risk_target.db") as conn:
            row = conn.execute(
                "SELECT \"limit\" FROM trading_limits WHERE desk = 'MACRO'"
            ).fetchone()
        assert row is not None and row[0] == 1_250_000

    def test_the_failed_changeset_left_the_target_alone(
        self, run: tuple[Path, str]
    ) -> None:
        directory, store_url = run
        with sqlite3.connect(directory / "risk_target.db") as conn:
            count = conn.execute(
                "SELECT count(*) FROM holidays WHERE day = '2026-12-25'"
            ).fetchone()[0]
        assert count == 1  # all-or-nothing: no duplicate, no partial write
        failed = [c for c in _changesets(store_url) if c.state is ChangesetState.FAILED]
        assert len(failed) == 1

    def test_the_rework_reached_revision_two(self, run: tuple[Path, str]) -> None:
        _, store_url = run
        reworked = [c for c in _changesets(store_url) if "PLATINUM" in c.title]
        assert len(reworked) == 1
        assert reworked[0].revision == 2
        assert reworked[0].state is ChangesetState.APPROVED

    def test_the_invalid_draft_is_still_a_draft_and_fails_validation(
        self, run: tuple[Path, str]
    ) -> None:
        directory, store_url = run
        loaded = load_workspace(directory / "ws.json")
        invalid = [c for c in _changesets(store_url) if "SYNTHETICS" in c.title]
        assert len(invalid) == 1
        changeset = invalid[0]
        assert changeset.state is ChangesetState.DRAFT

        # It fails on the cross-BACKEND cross-table rule: coverage lives in
        # crm, the referenced desks table in risk (D44).
        from bizkit.services.validation import ValidationService
        from bizkit.workspace.registry import FileTableRegistry

        def rows_for(ref: TableRef, columns: Sequence[str]) -> list[dict[str, object]]:
            target = loaded.config.targets[ref.backend]
            return get_backend_class(target.backend)(target.url).read_rows(ref, columns)

        config = FileTableRegistry(loaded.tables).lookup(changeset.table)
        assert config is not None
        report = ValidationService().validate(changeset, config.rules, rows_for)
        assert report.ok is False
        assert any(i.rule_id == "desk-registered-cross-backend" for i in report.issues)

    def test_uses_two_target_backends(self, run: tuple[Path, str]) -> None:
        directory, store_url = run
        assert (directory / "risk_target.db").exists()
        assert (directory / "crm_target.db").exists()
        backends = {c.table.backend for c in _changesets(store_url)}
        assert backends == {"risk", "crm"}
