"""End-to-end apply through the REST surface, against a real sqlite target.

Covers the whole chain: create → submit (validated) → approve → apply, with
the row actually landing in the target file, plus the three ways an apply
attempt can be refused or fail.
"""

import json
import sqlite3
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import httpx
import pytest

from bizkit.api.app import create_app
from bizkit.workspace.loader import load_workspace


def _workspace(tmp_path: Path, target: Path) -> Path:
    path = tmp_path / "ws.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "store_url": f"sqlite+pysqlite:///{tmp_path / 'store.db'}",
                "targets": {
                    "sample": {"backend": "sqlite", "url": f"sqlite:///{target}"}
                },
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
                                "not_null": True,
                            }
                        ],
                    }
                ],
                "grants": [
                    {"principal": "alice", "role": "maker", "scope": "sample/*/*"},
                    {"principal": "bob", "role": "checker", "scope": "sample/*/*"},
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def target_db(tmp_path: Path) -> Path:
    path = tmp_path / "target.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE fx_rates (pair TEXT PRIMARY KEY, rate REAL NOT NULL)"
        )
        conn.execute("INSERT INTO fx_rates VALUES ('EURUSD', 1.09)")
        conn.commit()
    return path


@pytest.fixture
async def client(
    tmp_path: Path, target_db: Path, migrate_store: Callable[[str], None]
) -> AsyncIterator[httpx.AsyncClient]:
    migrate_store(f"sqlite+pysqlite:///{tmp_path / 'store.db'}")
    app = create_app(workspace=load_workspace(_workspace(tmp_path, target_db)))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as async_client:
        yield async_client


def _as(user: str) -> dict[str, str]:
    return {"X-Bizkit-User": user}


def rows(db: Path) -> dict[str, float]:
    with sqlite3.connect(db) as conn:
        return dict(conn.execute("SELECT pair, rate FROM fx_rates").fetchall())


def _body(values: dict[str, object], submit_now: bool = True) -> dict[str, object]:
    return {
        "backend": "sample",
        "schema_name": None,
        "table": "fx_rates",
        "title": "Add rate",
        "description": "",
        "items": [{"op": "insert", "key": None, "values": values}],
        "submit_now": submit_now,
    }


async def _approved(client: httpx.AsyncClient, values: dict[str, object]) -> str:
    created = await client.post(
        "/api/v1/changesets", json=_body(values), headers=_as("alice")
    )
    assert created.status_code == 201, created.text
    changeset_id = created.json()["id"]
    approved = await client.post(
        f"/api/v1/changesets/{changeset_id}/approve",
        json={"reason": "ok"},
        headers=_as("bob"),
    )
    assert approved.status_code == 200, approved.text
    return str(changeset_id)


async def test_apply_writes_the_row_to_the_target(
    client: httpx.AsyncClient, target_db: Path
) -> None:
    changeset_id = await _approved(client, {"pair": "USDJPY", "rate": 155.2})

    response = await client.post(
        f"/api/v1/changesets/{changeset_id}/apply", headers=_as("bob")
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["changeset"]["state"] == "applied"
    assert payload["error"] is None
    assert rows(target_db)["USDJPY"] == 155.2


async def test_apply_appears_in_the_audit_trail(client: httpx.AsyncClient) -> None:
    changeset_id = await _approved(client, {"pair": "USDJPY", "rate": 155.2})
    await client.post(f"/api/v1/changesets/{changeset_id}/apply", headers=_as("bob"))

    audit = await client.get(
        f"/api/v1/changesets/{changeset_id}/audit", headers=_as("bob")
    )
    actions = [e["action"] for e in audit.json()]
    assert actions == ["create", "submit", "approve", "apply"]


async def test_a_maker_cannot_apply(client: httpx.AsyncClient, target_db: Path) -> None:
    # Action.APPLY belongs to the checker role in the default mapping.
    changeset_id = await _approved(client, {"pair": "USDJPY", "rate": 155.2})

    response = await client.post(
        f"/api/v1/changesets/{changeset_id}/apply", headers=_as("alice")
    )

    assert response.status_code == 403
    assert "USDJPY" not in rows(target_db)


async def test_applying_a_draft_is_a_conflict(
    client: httpx.AsyncClient, target_db: Path
) -> None:
    created = await client.post(
        "/api/v1/changesets",
        json=_body({"pair": "USDJPY", "rate": 155.2}, submit_now=False),
        headers=_as("alice"),
    )
    changeset_id = created.json()["id"]

    response = await client.post(
        f"/api/v1/changesets/{changeset_id}/apply", headers=_as("bob")
    )

    assert response.status_code == 409
    assert "USDJPY" not in rows(target_db)


async def test_a_target_rejection_is_a_200_with_failed_state(
    client: httpx.AsyncClient, target_db: Path
) -> None:
    # EURUSD already exists, so the insert trips the primary key. The attempt
    # is a recorded event, so it is a result rather than an HTTP error.
    changeset_id = await _approved(client, {"pair": "EURUSD", "rate": 2.0})

    response = await client.post(
        f"/api/v1/changesets/{changeset_id}/apply", headers=_as("bob")
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is False
    assert payload["changeset"]["state"] == "failed"
    assert payload["error"] is not None
    assert rows(target_db)["EURUSD"] == 1.09  # untouched


async def test_a_failed_apply_can_be_retried_after_the_obstacle_clears(
    client: httpx.AsyncClient, target_db: Path
) -> None:
    changeset_id = await _approved(client, {"pair": "EURUSD", "rate": 2.0})
    first = await client.post(
        f"/api/v1/changesets/{changeset_id}/apply", headers=_as("bob")
    )
    assert first.json()["changeset"]["state"] == "failed"

    with sqlite3.connect(target_db) as conn:
        conn.execute("DELETE FROM fx_rates WHERE pair = 'EURUSD'")
        conn.commit()

    second = await client.post(
        f"/api/v1/changesets/{changeset_id}/apply", headers=_as("bob")
    )

    assert second.json()["ok"] is True
    assert rows(target_db)["EURUSD"] == 2.0


async def test_submit_is_blocked_by_validation(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/changesets",
        json=_body({"pair": "USDJPY", "rate": -1}),
        headers=_as("alice"),
    )
    assert response.status_code == 422
    assert "rate" in response.text


async def test_validate_reports_without_transitioning(
    client: httpx.AsyncClient,
) -> None:
    created = await client.post(
        "/api/v1/changesets",
        json=_body({"pair": "USDJPY", "rate": -1}, submit_now=False),
        headers=_as("alice"),
    )
    changeset_id = created.json()["id"]

    response = await client.post(
        f"/api/v1/changesets/{changeset_id}/validate", headers=_as("alice")
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is False
    assert payload["issues"][0]["rule_id"] == "rate-positive"
    assert payload["issues"][0]["column"] == "rate"

    detail = await client.get(
        f"/api/v1/changesets/{changeset_id}", headers=_as("alice")
    )
    assert detail.json()["state"] == "draft"
