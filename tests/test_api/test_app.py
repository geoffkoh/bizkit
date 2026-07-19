"""API smoke tests over the ASGI transport (no server process)."""

from collections.abc import AsyncIterator

import httpx
import pytest

from bizkit.api.app import create_app
from bizkit.config import BizkitConfig


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(BizkitConfig(store_url="sqlite+pysqlite:///:memory:"))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as async_client:
        yield async_client


async def test_health(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["store"] is True


async def test_changesets_empty(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/changesets")
    assert response.status_code == 200
    assert response.json() == []


async def test_changeset_missing_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/changesets/nope")
    assert response.status_code == 404


async def test_tables_empty_without_workspace(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/tables")
    assert response.status_code == 200
    assert response.json() == []


async def test_unimplemented_endpoints_501(client: httpx.AsyncClient) -> None:
    assert (await client.post("/api/v1/changesets/x/validate")).status_code == 501


async def test_import_missing_changeset_404(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/changesets/x/items/import", content=b"a,b\n1,2\n"
    )
    assert response.status_code == 404
