# mushin — Claude instructions

## What this project is

Mushin (무심, 無心 — "no-mind") is a general personal progress tracker. Log how
often you do any activity and watch it add up — entries, counts, and streaks. Multi-user from day one; UI strings centralized for i18n.

Stack: FastAPI + uv + Uvicorn. Tailwind CSS v4 + HTMX + vanilla JS (web), Hyperview/HXML (mobile), SQLite.
Hosting: Ubuntu 24.04 (production via Caddy + systemd).

## Current state

- Live at: https://mushin.aqnas.xyz
- Local dev: `./run.sh` (port 8000)
- Repo: github.com/yjaquinas/mushin
- Production path: `/opt/mushin/mushin/` on `aqnas-prod`
- Production port: 8013

## Domain model

One level: activity → entry.

Architecture: one FastAPI backend, two hypermedia renderers — HTMX (web/PWA) and
HXML (Hyperview native) — over a shared renderer-agnostic domain/service layer.
Online-first.

## Auth + accounts

**Account required to start.** Every new user must sign up (username + password) before logging an entry.
Username is load-bearing infrastructure — every activity lives at
`/@{username}/{slug}` — so a no-username guest account can't participate in
the core shareable-URL feature.

**Visibility is three-tier (not binary).**
`public` = whole record incl. notes visible to anyone.
`private` = a non-connected visitor sees the **character sheet** at `/@{username}` (activity names + counts, cards not clickable) but **cannot open `/@{username}/{slug}`** — that 303-redirects to `/@{username}`. A **fellow** (accepted mutual connection, after a separate sharing-consent) sees the full record incl. entries and free-text notes on either account.
`private` no longer means "hidden": all accounts are searchable by username/display name, and a private account's activity _names_ are visible to any searcher. The single fail-closed authority for every visibility decision is `app/services/profiles.py::viewer_capability` / `can_view_activity_detail` — never inline a `visibility` check in a handler, never cache a capability.

## Key constraints

- Every data query is scoped by `owner_id` — multi-user isolation is non-negotiable.
- UI strings stay centralized for i18n (English at launch; other locales are a later addition).
- {add further externally-committed constraints as they emerge}

## Deployment

Push to `main` triggers `.github/workflows/deploy.yml`, which SSHes into
the production host and runs `deploy/run.sh` in this repo. See the studio's
`deploy-procedure` skill for the full model.

`deploy/run.sh` handles: git sync (`sg + fetch + reset --hard`),
`uv sync --frozen --no-dev`, optional Tailwind build, conditional Caddy
config sync from `infra/mushin.caddy`, `systemctl restart`, and
health check via `GET /health`.

GitHub secrets:

- `SSH_HOST` — production host IP or DNS
- `SSH_PRIVATE_KEY` — deploy user's SSH private key

## Development workflow

Local: `./run.sh` (starts uvicorn with `--reload` and, if applicable,
the Tailwind watcher). URL: http://127.0.0.1:8000.

For per-project Claude Code rules and skills, see `.claude/` in this repo
(loaded automatically when Claude Code runs from the project root).

Route files live under `app/routes/` split by surface (`web/`, `public/`,
`data_io.py`, `mobile.py`), one file per route group, 150-line ceiling.
