"""Smoke test: the app boots and the health endpoint answers."""

from __future__ import annotations

from httpx import AsyncClient

from app import ui_strings


async def test_health_returns_ok(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.text == "ok"


async def test_index_renders(client: AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "無心" in resp.text
    assert ui_strings.ENTRY_AUTH_TAB_LOGIN in resp.text
