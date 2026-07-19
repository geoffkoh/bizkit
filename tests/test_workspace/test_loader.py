"""Workspace file loading: versioning, env indirection, fingerprint (D22/D23/D30)."""

import json
from pathlib import Path

import pytest

from bizkit.exceptions import ConfigError
from bizkit.workspace.loader import (
    check_no_literal_secrets,
    load_workspace,
)


def _write(tmp_path: Path, data: dict[str, object]) -> Path:
    path = tmp_path / "bizkit.workspace.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _minimal(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "version": 1,
        "store_url": "sqlite:///test.db",
        "tables": [
            {
                "backend": "sample",
                "table": "fx_rates",
                "rules": [
                    {
                        "kind": "constraint",
                        "rule_id": "rate-positive",
                        "column": "rate",
                        "min_value": 0,
                    }
                ],
            }
        ],
        "grants": [{"principal": "alice", "role": "maker", "scope": "sample/*/*"}],
    }
    data.update(overrides)
    return data


def test_load_minimal_workspace(tmp_path: Path) -> None:
    loaded = load_workspace(_write(tmp_path, _minimal()))
    assert loaded.config.store_url == "sqlite:///test.db"
    assert len(loaded.tables) == 1
    assert loaded.tables[0].rules[0].rule_id == "rate-positive"
    assert loaded.grants[0].principal == "alice"
    assert len(loaded.fingerprint) == 64


def test_version_is_required(tmp_path: Path) -> None:
    data = _minimal()
    del data["version"]
    with pytest.raises(ConfigError):
        load_workspace(_write(tmp_path, data))


def test_unknown_version_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_workspace(_write(tmp_path, _minimal(version=99)))


def test_unknown_keys_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_workspace(_write(tmp_path, _minimal(grnats=[])))


def test_env_indirection_resolves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEST_STORE_URL", "sqlite:///from-env.db")
    loaded = load_workspace(_write(tmp_path, _minimal(store_url="${TEST_STORE_URL}")))
    assert loaded.config.store_url == "sqlite:///from-env.db"


def test_missing_env_var_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING_VAR", raising=False)
    with pytest.raises(ConfigError):
        load_workspace(_write(tmp_path, _minimal(store_url="${MISSING_VAR}")))


def test_fingerprint_is_over_unresolved_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write(tmp_path, _minimal(store_url="${TEST_STORE_URL}"))
    monkeypatch.setenv("TEST_STORE_URL", "sqlite:///a.db")
    first = load_workspace(path).fingerprint
    monkeypatch.setenv("TEST_STORE_URL", "sqlite:///b.db")
    second = load_workspace(path).fingerprint
    assert first == second


def test_literal_secret_detection() -> None:
    dirty = '{"url": "postgresql://user:hunter2@host/db"}'
    findings = check_no_literal_secrets(dirty)
    assert findings == ["://user:***@"]
    assert "hunter2" not in "".join(findings)
    clean = '{"url": "${PG_URL}"}'
    assert check_no_literal_secrets(clean) == []


def test_invalid_scope_in_grant_fails(tmp_path: Path) -> None:
    data = _minimal(
        grants=[{"principal": "a", "role": "maker", "scope": "not-a-scope"}]
    )
    with pytest.raises(ConfigError):
        load_workspace(_write(tmp_path, data))
