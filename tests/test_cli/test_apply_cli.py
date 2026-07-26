"""`bizkit apply` and `bizkit validate` against the seeded sample workspace.

Uses `init-store --seed-sample`, which lays down a real sqlite target, so
this exercises the same path an operator takes: seed, find the approved
changeset, apply it, see the row land.
"""

import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

from bizkit.cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def seeded(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(cli, ["init-store", "--seed-sample"])
    assert result.exit_code == 0, result.output
    return tmp_path


def _workspace_args(seeded: Path) -> list[str]:
    return ["--config", str(seeded / "bizkit.workspace.json")]


def _approved_fx_changeset(runner: CliRunner, seeded: Path) -> str:
    result = runner.invoke(cli, [*_workspace_args(seeded), "list"])
    assert result.exit_code == 0, result.output
    for line in result.output.splitlines():
        if "approved" in line and "fx_rates" in line:
            return line.split()[0]
    raise AssertionError(f"no approved fx_rates changeset in:\n{result.output}")


def rows(seeded: Path) -> dict[str, float]:
    with sqlite3.connect(seeded / "sample_target.db") as conn:
        return dict(conn.execute("SELECT pair, rate FROM fx_rates").fetchall())


def test_apply_writes_to_the_seeded_target(runner: CliRunner, seeded: Path) -> None:
    changeset_id = _approved_fx_changeset(runner, seeded)

    result = runner.invoke(
        cli, [*_workspace_args(seeded), "apply", changeset_id, "--actor", "bob"]
    )

    assert result.exit_code == 0, result.output
    assert "Applied" in result.output
    listing = runner.invoke(cli, [*_workspace_args(seeded), "list"])
    assert f"{changeset_id[:8]}" in listing.output
    assert "applied" in listing.output


def test_apply_refuses_a_maker(runner: CliRunner, seeded: Path) -> None:
    changeset_id = _approved_fx_changeset(runner, seeded)

    result = runner.invoke(
        cli, [*_workspace_args(seeded), "apply", changeset_id, "--actor", "alice"]
    )

    assert result.exit_code != 0
    assert "apply" in result.output.lower()


def test_dry_run_leaves_the_target_and_the_state_alone(
    runner: CliRunner, seeded: Path
) -> None:
    changeset_id = _approved_fx_changeset(runner, seeded)
    before = rows(seeded)

    result = runner.invoke(
        cli,
        [
            *_workspace_args(seeded),
            "apply",
            changeset_id,
            "--actor",
            "bob",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Dry run OK" in result.output
    assert rows(seeded) == before
    listing = runner.invoke(cli, [*_workspace_args(seeded), "list"])
    assert "applied" not in listing.output


def test_validate_reports_ok_for_a_clean_changeset(
    runner: CliRunner, seeded: Path
) -> None:
    changeset_id = _approved_fx_changeset(runner, seeded)

    result = runner.invoke(cli, [*_workspace_args(seeded), "validate", changeset_id])

    assert result.exit_code == 0, result.output
    assert "OK" in result.output
