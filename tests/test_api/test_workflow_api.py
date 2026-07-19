"""End-to-end API tests for the workflow, comments, and tables routes."""

import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from bizkit.api.app import create_app
from bizkit.workspace.loader import load_workspace


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    workspace_path = tmp_path / "ws.json"
    workspace_path.write_text(
        json.dumps(
            {
                "version": 1,
                "store_url": "sqlite+pysqlite:///:memory:",
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
                "grants": [
                    {
                        "principal": "alice",
                        "role": "maker",
                        "scope": "sample/*/*",
                    },
                    {
                        "principal": "bob",
                        "role": "checker",
                        "scope": "sample/*/*",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    app = create_app(workspace=load_workspace(workspace_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as async_client:
        yield async_client


def _as(user: str) -> dict[str, str]:
    return {"X-Bizkit-User": user}


_CREATE_BODY = {
    "backend": "sample",
    "schema_name": None,
    "table": "fx_rates",
    "title": "Add JPY rate",
    "description": "test",
    "items": [{"op": "insert", "key": None, "values": {"rate": 155.2}}],
    "submit_now": False,
}


async def test_me_reflects_header(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/me", headers=_as("alice"))
    assert response.json() == {"user": "alice"}


async def test_tables_show_caller_affordances(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/tables", headers=_as("alice"))
    (table,) = response.json()
    assert table["path"] == "sample//fx_rates"
    assert table["rule_count"] == 1
    assert table["actions"]["submit"] is True
    assert table["actions"]["approve"] is False

    response = await client.get("/api/v1/tables", headers=_as("bob"))
    (table,) = response.json()
    assert table["actions"]["submit"] is False
    assert table["actions"]["approve"] is True


async def test_full_workflow_via_api(client: httpx.AsyncClient) -> None:
    created = await client.post(
        "/api/v1/changesets", json=_CREATE_BODY, headers=_as("alice")
    )
    assert created.status_code == 201, created.text
    changeset = created.json()
    assert changeset["state"] == "draft"
    assert changeset["items"][0]["values"] == {"rate": 155.2}
    cs_id = changeset["id"]

    submitted = await client.post(
        f"/api/v1/changesets/{cs_id}/submit", headers=_as("alice")
    )
    assert submitted.json()["state"] == "submitted"
    assert submitted.json()["revision"] == 1

    comment = await client.post(
        f"/api/v1/changesets/{cs_id}/comments",
        json={"body": "Which close is this?", "parent_id": None},
        headers=_as("bob"),
    )
    assert comment.status_code == 201
    reply = await client.post(
        f"/api/v1/changesets/{cs_id}/comments",
        json={"body": "Tokyo close.", "parent_id": comment.json()["id"]},
        headers=_as("alice"),
    )
    assert reply.status_code == 201
    thread = (await client.get(f"/api/v1/changesets/{cs_id}/comments")).json()
    assert [c["author"] for c in thread] == ["bob", "alice"]
    assert thread[1]["parent_id"] == comment.json()["id"]

    approved = await client.post(
        f"/api/v1/changesets/{cs_id}/approve",
        json={"reason": "ok"},
        headers=_as("bob"),
    )
    assert approved.json()["state"] == "approved"

    decisions = (await client.get(f"/api/v1/changesets/{cs_id}/decisions")).json()
    assert decisions == [
        {
            "revision": 1,
            "checker": "bob",
            "decision": "approve",
            "reason": "ok",
            "decided_at": decisions[0]["decided_at"],
            "self_approved": False,
        }
    ]

    audit = (await client.get(f"/api/v1/changesets/{cs_id}/audit")).json()
    assert [e["action"] for e in audit] == [
        "create",
        "submit",
        "comment",
        "comment",
        "approve",
    ]


async def test_unauthorized_create_403(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/changesets", json=_CREATE_BODY, headers=_as("mallory")
    )
    assert response.status_code == 403


async def test_maker_cannot_approve_403(client: httpx.AsyncClient) -> None:
    created = await client.post(
        "/api/v1/changesets",
        json={**_CREATE_BODY, "submit_now": True},
        headers=_as("alice"),
    )
    cs_id = created.json()["id"]
    response = await client.post(
        f"/api/v1/changesets/{cs_id}/approve", headers=_as("alice")
    )
    assert response.status_code == 403


async def test_illegal_transition_409(client: httpx.AsyncClient) -> None:
    created = await client.post(
        "/api/v1/changesets", json=_CREATE_BODY, headers=_as("alice")
    )
    cs_id = created.json()["id"]
    response = await client.post(
        f"/api/v1/changesets/{cs_id}/approve", headers=_as("bob")
    )
    assert response.status_code == 409


async def test_reject_needs_reason_and_rework(
    client: httpx.AsyncClient,
) -> None:
    created = await client.post(
        "/api/v1/changesets",
        json={**_CREATE_BODY, "submit_now": True},
        headers=_as("alice"),
    )
    cs_id = created.json()["id"]

    no_reason = await client.post(
        f"/api/v1/changesets/{cs_id}/reject",
        json={"reason": ""},
        headers=_as("bob"),
    )
    assert no_reason.status_code == 403

    rejected = await client.post(
        f"/api/v1/changesets/{cs_id}/reject",
        json={"reason": "wrong rate"},
        headers=_as("bob"),
    )
    assert rejected.json()["state"] == "rejected"

    reworked = await client.post(
        f"/api/v1/changesets/{cs_id}/rework", headers=_as("alice")
    )
    assert reworked.json()["state"] == "draft"


async def test_missing_changeset_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/changesets/nope")
    assert response.status_code == 404
