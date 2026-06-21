---
paths:
  - "app/**"
  - "tests/**"
---

# Python backend conventions

Path-scoped: loads when Claude is editing `app/**` or `tests/**`. Fill in the concrete rules as conventions settle — this skeleton lists the expected topics.

## Invocation

- All Python scripts and tools run via `uv run` from the project root. Never call `python3` directly in docs, CI, or scripts — `uv run python ...` keeps the venv honest.
- Lockfile is authoritative. CI uses `uv sync --frozen`.

## Imports and modules

- Prefer explicit imports over `from x import *`.
- `app/routes/` contains thin handlers; business logic lives in `app/services/`.
- `app/models/db.py` is the only module that opens SQLite connections.

## Logging

- `structlog` is the logger. No `print()` outside of tests and one-off scripts.
- Level defaults to `INFO` in production; `DEBUG` only behind a dev flag.

## Database

- One SQLite connection per request via the `connect()` context manager in `app/models/db.py`.
- Always parameterize queries (`?` placeholders). Never format user input into SQL.
- Migrations are append-only in `app/models/migrations/`, integer-prefixed.
- See `sqlite-conventions` skill for the full pattern.

## Linting

- `ruff check` passes before any commit.
- `ruff format` is the formatter.
- No unused imports or variables in committed code.

## Testing

- pytest for unit and integration tests.
- Integration tests use `httpx.AsyncClient` against the FastAPI app.
- E2E tests use Playwright via the `playwright-cli` skill (Bash-invoked, not MCP).
- New features land with tests — see `tests.md` rule.

## Project-specific additions

- Raw SQL only (stdlib `sqlite3`), no ORM. Per-request connection context manager, never a global connection. WAL + `foreign_keys=ON`.
- Every data-access function takes `owner_id` as a **required argument**; provide a helper so it can't be omitted. Multi-user isolation is non-negotiable.
- Domain/service code in `app/services/` is renderer-agnostic: no HTTP, no Jinja, no HXML — returns plain data both renderers consume.
- Secrets via `os.getenv(...)` only; documented in `.env.example`.
- Password hashing is Argon2id (`argon2-cffi`); sessions are `HttpOnly; Secure; SameSite=Lax`.
