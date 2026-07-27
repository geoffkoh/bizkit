"""The `bizkit store` schema commands (spec D45)."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from bizkit.cli.main import cli
from bizkit.store import schema
from bizkit.store.engine import create_store_engine


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def store_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path}/store.db"


def test_a_command_on_an_uninitialized_store_says_what_to_run(
    runner: CliRunner, store_url: str
) -> None:
    """No implicit migration: the command stops and names the fix (D45)."""
    result = runner.invoke(cli, ["--store-url", store_url, "list"])

    assert result.exit_code != 0
    assert "init-store" in result.output


def test_upgrade_creates_then_reports_no_work(
    runner: CliRunner, store_url: str
) -> None:
    first = runner.invoke(cli, ["--store-url", store_url, "store", "upgrade"])
    assert first.exit_code == 0, first.output
    assert schema.head_revision() in first.output

    second = runner.invoke(cli, ["--store-url", store_url, "store", "upgrade"])
    assert second.exit_code == 0, second.output
    assert "nothing to do" in second.output


def test_current_reports_head_after_init(runner: CliRunner, store_url: str) -> None:
    assert runner.invoke(cli, ["--store-url", store_url, "init-store"]).exit_code == 0

    result = runner.invoke(cli, ["--store-url", store_url, "store", "current"])

    assert result.exit_code == 0, result.output
    assert "up to date" in result.output
    assert schema.head_revision() in result.output


def test_current_flags_a_store_with_no_schema(
    runner: CliRunner, store_url: str
) -> None:
    result = runner.invoke(cli, ["--store-url", store_url, "store", "current"])

    assert result.exit_code == 0, result.output
    assert "UPGRADE NEEDED" in result.output


def test_upgrade_sql_emits_ddl_and_creates_nothing(
    runner: CliRunner, store_url: str, tmp_path: Path
) -> None:
    result = runner.invoke(cli, ["--store-url", store_url, "store", "upgrade", "--sql"])

    assert result.exit_code == 0, result.output
    assert "CREATE TABLE bizkit_changesets" in result.output
    assert not (tmp_path / "store.db").exists()


def test_stamp_records_a_dba_applied_upgrade(runner: CliRunner, store_url: str) -> None:
    from bizkit.store.models import Base

    engine = create_store_engine(store_url)
    Base.metadata.create_all(engine)  # stand-in for DBA-applied DDL

    result = runner.invoke(
        cli, ["--store-url", store_url, "store", "stamp", schema.head_revision()]
    )

    assert result.exit_code == 0, result.output
    assert runner.invoke(cli, ["--store-url", store_url, "list"]).exit_code == 0


def test_history_lists_the_chain(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["store", "history"])

    assert result.exit_code == 0, result.output
    assert "0001" in result.output


def test_store_group_works_without_a_workspace_file(
    runner: CliRunner, store_url: str, tmp_path: Path
) -> None:
    """Schema plumbing must run before a workspace exists (D45)."""
    missing = tmp_path / "nope.json"

    result = runner.invoke(
        cli, ["--config", str(missing), "--store-url", store_url, "store", "history"]
    )

    assert result.exit_code == 0, result.output
