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
