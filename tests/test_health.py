"""Smoke test: the app boots and the health endpoint answers."""

from __future__ import annotations

from httpx import AsyncClient


async def test_health_returns_ok(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.text == "ok"


async def test_index_renders(client: AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "無心" in resp.text
    assert "그냥 시작하기" in resp.text
