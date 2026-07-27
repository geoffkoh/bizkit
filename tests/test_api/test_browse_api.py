"""Table browsing endpoints: columns/rows with view enforcement (D38/D39)."""

import json
import sqlite3
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import httpx
import pytest

from bizkit.api.app import create_app
from bizkit.workspace.loader import load_workspace


@pytest.fixture
async def client(
    tmp_path: Path, migrate_store: Callable[[str], None]
) -> AsyncIterator[httpx.AsyncClient]:
    target_db = tmp_path / "target.db"
    with sqlite3.connect(target_db) as conn:
        conn.execute(
            "CREATE TABLE fx_rates (pair TEXT PRIMARY KEY, rate REAL NOT NULL)"
        )
        conn.executemany(
            "INSERT INTO fx_rates VALUES (?, ?)",
            [(f"PAIR{i:03d}", float(i)) for i in range(60)],
        )
        conn.commit()

    workspace_path = tmp_path / "ws.json"
    workspace_path.write_text(
        json.dumps(
            {
                "version": 1,
                "store_url": f"sqlite+pysqlite:///{tmp_path / 'store.db'}",
                "targets": {
                    "sample": {
                        "backend": "sqlite",
                        "url": f"sqlite:///{target_db}",
                    }
                },
                "tables": [{"backend": "sample", "table": "fx_rates"}],
                "grants": [
                    {
                        "principal": "dave",
                        "role": "reader",
                        "scope": "sample/*/*",
                    },
                    {
                        "principal": "alice",
                        "role": "maker",
                        "scope": "sample/*/*",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    migrate_store(f"sqlite+pysqlite:///{tmp_path / 'store.db'}")
    app = create_app(workspace=load_workspace(workspace_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as async_client:
        yield async_client


def _as(user: str) -> dict[str, str]:
    return {"X-Bizkit-User": user}


async def test_reader_sees_columns(client: httpx.AsyncClient) -> None:
    response = await client.get(
        "/api/v1/tables/sample/-/fx_rates/columns", headers=_as("dave")
    )
    assert response.status_code == 200
    by_name = {c["name"]: c for c in response.json()}
    assert by_name["pair"]["primary_key"] is True
    assert by_name["rate"]["type"] == "decimal"


async def test_reader_sees_paged_rows(client: httpx.AsyncClient) -> None:
    response = await client.get(
        "/api/v1/tables/sample/-/fx_rates/rows?page=2&page_size=50",
        headers=_as("dave"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 60
    assert body["page"] == 2
    assert len(body["rows"]) == 10
    assert body["rows"][0]["pair"] == "PAIR050"


async def test_rows_server_side_search_sort(client: httpx.AsyncClient) -> None:
    # 60 rows PAIR000..PAIR059, rate = i. Search narrows, total is filtered.
    response = await client.get(
        "/api/v1/tables/sample/-/fx_rates/rows?q=PAIR05&sort=rate&direction=desc",
        headers=_as("dave"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 10  # PAIR050..PAIR059
    assert body["rows"][0]["pair"] == "PAIR059"
    assert body["rows"][-1]["pair"] == "PAIR050"


async def test_rows_unknown_sort_column_422(client: httpx.AsyncClient) -> None:
    response = await client.get(
        "/api/v1/tables/sample/-/fx_rates/rows?sort=bogus", headers=_as("dave")
    )
    assert response.status_code == 422


async def test_no_view_grant_403(client: httpx.AsyncClient) -> None:
    response = await client.get(
        "/api/v1/tables/sample/-/fx_rates/rows", headers=_as("mallory")
    )
    assert response.status_code == 403


async def test_unregistered_table_404(client: httpx.AsyncClient) -> None:
    response = await client.get(
        "/api/v1/tables/sample/-/nope/rows", headers=_as("dave")
    )
    assert response.status_code == 404


async def test_tables_reports_reader_affordances(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/v1/tables", headers=_as("dave"))
    (table,) = response.json()
    assert table["actions"]["view"] is True
    assert table["actions"]["submit"] is False
    assert table["actions"]["comment"] is False
    assert table["max_changeset_items"] == 10000


async def test_csv_import_via_api(client: httpx.AsyncClient) -> None:
    created = await client.post(
        "/api/v1/changesets",
        json={
            "backend": "sample",
            "schema_name": None,
            "table": "fx_rates",
            "title": "Bulk import",
            "description": "",
            "items": [],
            "submit_now": False,
        },
        headers=_as("alice"),
    )
    cs_id = created.json()["id"]

    response = await client.post(
        f"/api/v1/changesets/{cs_id}/items/import?mode=append&filename=r.csv",
        content=b"_op,pair,rate\ninsert,NEW001,1.5\nupdate,PAIR001,9.9\n",
        headers=_as("alice"),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["items_added"] == 2

    detail = await client.get(f"/api/v1/changesets/{cs_id}")
    assert detail.json()["item_count"] == 2

    audit = (await client.get(f"/api/v1/changesets/{cs_id}/audit")).json()
    assert audit[-1]["action"] == "import"
    assert "sha256:" in audit[-1]["detail"]


async def test_csv_import_reports_errors_without_adding(
    client: httpx.AsyncClient,
) -> None:
    created = await client.post(
        "/api/v1/changesets",
        json={
            "backend": "sample",
            "schema_name": None,
            "table": "fx_rates",
            "title": "Bad import",
            "description": "",
            "items": [],
            "submit_now": False,
        },
        headers=_as("alice"),
    )
    cs_id = created.json()["id"]
    response = await client.post(
        f"/api/v1/changesets/{cs_id}/items/import",
        content=b"pair,rate\nX,notanumber\n",
        headers=_as("alice"),
    )
    body = response.json()
    assert body["ok"] is False
    assert body["items_added"] == 0
    assert body["issues"][0]["column"] == "rate"
    detail = await client.get(f"/api/v1/changesets/{cs_id}")
    assert detail.json()["item_count"] == 0


async def test_import_denied_for_reader(client: httpx.AsyncClient) -> None:
    created = await client.post(
        "/api/v1/changesets",
        json={
            "backend": "sample",
            "schema_name": None,
            "table": "fx_rates",
            "title": "Mine",
            "description": "",
            "items": [],
            "submit_now": False,
        },
        headers=_as("alice"),
    )
    cs_id = created.json()["id"]
    response = await client.post(
        f"/api/v1/changesets/{cs_id}/items/import",
        content=b"pair,rate\nA,1\n",
        headers=_as("dave"),
    )
    assert response.status_code == 403
