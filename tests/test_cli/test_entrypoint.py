"""CLI smoke tests via the click runner."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from bizkit.cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_help_lists_commands(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    for command in ("init-store", "list", "serve", "config", "expire"):
        assert command in result.output


def test_init_store_and_list(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    store_url = f"sqlite:///{tmp_path}/store.db"
    result = runner.invoke(cli, ["--store-url", store_url, "init-store"])
    assert result.exit_code == 0, result.output
    result = runner.invoke(cli, ["--store-url", store_url, "list"])
    assert result.exit_code == 0, result.output
    assert "No changesets" in result.output


def test_seed_sample_creates_pending_changeset(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    store_url = f"sqlite:///{tmp_path}/store.db"
    result = runner.invoke(
        cli, ["--store-url", store_url, "init-store", "--seed-sample"]
    )
    assert result.exit_code == 0, result.output
    assert Path("sample_target.db").exists()
    assert Path("bizkit.workspace.json").exists()

    result = runner.invoke(cli, ["--store-url", store_url, "list"])
    assert result.exit_code == 0, result.output
    assert "submitted" in result.output
    assert "alice" in result.output


def test_config_validate_and_schema(runner: CliRunner, tmp_path: Path) -> None:
    workspace = tmp_path / "ws.json"
    workspace.write_text(
        json.dumps(
            {
                "version": 1,
                "store_url": "sqlite:///x.db",
                "tables": [
                    {
                        "backend": "sample",
                        "table": "fx_rates",
                        "allow_self_approval": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = runner.invoke(cli, ["config", "validate", str(workspace)])
    assert result.exit_code == 0, result.output
    assert "fingerprint sha256:" in result.output
    assert "SELF-APPROVAL LIVE" in result.output

    result = runner.invoke(cli, ["config", "schema"])
    assert result.exit_code == 0, result.output
    schema = json.loads(result.output)
    assert "version" in schema.get("required", [])


def test_config_validate_rejects_literal_secrets(
    runner: CliRunner, tmp_path: Path
) -> None:
    workspace = tmp_path / "ws.json"
    workspace.write_text(
        json.dumps({"version": 1, "store_url": "postgresql://u:hunter2@h/db"}),
        encoding="utf-8",
    )
    result = runner.invoke(cli, ["config", "validate", str(workspace)])
    assert result.exit_code != 0
    assert "ENV_VAR" in result.output


def test_stub_commands_fail_clearly(runner: CliRunner) -> None:
    # `apply` and `validate` are implemented now; these remain stubs.
    for name in ("show", "submit", "review", "comment"):
        result = runner.invoke(cli, [name])
        assert result.exit_code != 0
        assert "not implemented" in result.output.lower()


def test_missing_config_path_is_an_error_not_a_silent_fallback(
    runner: CliRunner, tmp_path: Path
) -> None:
    # Silently ignoring an explicit --config degrades to "no grants, no
    # targets", which surfaces much later as a confusing AccessDenied.
    result = runner.invoke(cli, ["--config", str(tmp_path / "nope.json"), "list"])
    assert result.exit_code != 0
    assert "nope.json" in result.output
    assert "does not exist" in result.output.lower()


def test_init_store_may_point_config_at_a_file_it_will_create(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `init-store --seed-sample` writes the workspace file at --config's path,
    # so for this one command a not-yet-existing path is legitimate.
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "fresh.workspace.json"
    result = runner.invoke(
        cli, ["--config", str(target), "init-store", "--seed-sample"]
    )
    assert result.exit_code == 0, result.output
    assert target.exists()
    # And it is usable immediately afterwards.
    listing = runner.invoke(cli, ["--config", str(target), "list"])
    assert listing.exit_code == 0, listing.output


def test_existing_config_still_loads(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    workspace = tmp_path / "ws.json"
    workspace.write_text(
        json.dumps({"version": 1, "store_url": f"sqlite:///{tmp_path}/s.db"}),
        encoding="utf-8",
    )
    # The store must exist before a command opens it (D45: no implicit migrate).
    assert runner.invoke(cli, ["--config", str(workspace), "init-store"]).exit_code == 0
    result = runner.invoke(cli, ["--config", str(workspace), "list"])
    assert result.exit_code == 0, result.output


def test_list_scenarios_names_both_and_marks_the_default(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["init-store", "--list-scenarios"])
    assert result.exit_code == 0, result.output
    assert "sample (default)" in result.output
    assert "enterprise" in result.output


def test_seed_sample_is_an_alias_for_the_default_scenario(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Back-compat: --seed-sample predates --scenario and must keep working.
    monkeypatch.chdir(tmp_path)
    store_url = f"sqlite:///{tmp_path}/store.db"
    result = runner.invoke(
        cli, ["--store-url", store_url, "init-store", "--seed-sample"]
    )
    assert result.exit_code == 0, result.output
    assert "'sample'" in result.output
    assert Path("sample_target.db").exists()


def test_scenario_enterprise_seeds_two_targets(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    store_url = f"sqlite:///{tmp_path}/store.db"
    result = runner.invoke(
        cli, ["--store-url", store_url, "init-store", "--scenario", "enterprise"]
    )
    assert result.exit_code == 0, result.output
    assert Path("risk_target.db").exists()
    assert Path("crm_target.db").exists()
    listing = runner.invoke(cli, ["--store-url", store_url, "list"])
    assert "applied" in listing.output
    assert "failed" in listing.output


def test_an_unknown_scenario_is_rejected_with_the_choices(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["init-store", "--scenario", "nope"])
    assert result.exit_code != 0
    assert "enterprise" in result.output and "sample" in result.output


def test_init_store_without_seeding_creates_no_workspace(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        cli, ["--store-url", f"sqlite:///{tmp_path}/store.db", "init-store"]
    )
    assert result.exit_code == 0, result.output
    assert not Path("bizkit.workspace.json").exists()
    assert not Path("sample_target.db").exists()
