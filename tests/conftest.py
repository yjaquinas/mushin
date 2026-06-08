"""Shared pytest fixtures for Mushin.

See .claude/rules/tests.md for layout and conventions. Integration tests use
httpx.AsyncClient against the FastAPI app directly; never run against the dev DB.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncClient:
    """Async HTTP client bound to the FastAPI app (no network)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
