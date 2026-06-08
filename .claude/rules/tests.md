---
paths:
  - "tests/**"
---

# Testing conventions

Path-scoped: loads when Claude is editing or generating tests. Fill in project-specific additions as conventions settle.

## Layout

- `tests/unit/` — fast tests for pure functions and small units.
- `tests/integration/` — tests that touch the FastAPI app, database, or filesystem.
- `tests/e2e/` — Playwright tests driven through the Playwright MCP.
- `tests/conftest.py` — shared fixtures (DB setup/teardown, test client, etc.).

## Test naming

- Files: `test_{module_under_test}.py`. `app/services/auth.py` → `tests/unit/test_auth.py`.
- Functions: `test_{behavior}` — describe the behavior, not the implementation. `test_login_rejects_wrong_password` beats `test_login_path_2`.

## Running

- `uv run pytest` — full suite.
- `uv run pytest tests/unit/` — fast pass during development.
- `uv run pytest -k "auth"` — filter by name.

## Patterns

- Integration tests use `httpx.AsyncClient` against the FastAPI app directly (no network).
- DB fixtures create a fresh SQLite at `./tests/fixtures/test.db` or use `:memory:`. Never run tests against the dev database.
- E2E tests use the Playwright MCP — not a bundled Playwright. This avoids shipping a headless browser inside the project repo.

## What gets a test

- Every new route gets at least one integration test covering success and one covering failure.
- Every new service function with logic (not pure passthrough) gets a unit test.
- Bug fixes include a test that would have failed against the bug.
- UI-only changes (copy, colors, spacing) don't require tests.

## Project-specific additions

_(Add project-specific fixtures, helpers, or policies here.)_
