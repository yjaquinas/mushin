# mushin — Claude instructions

## What this project is

Mushin (무심, 無心 — "no-mind") is a general personal progress tracker. Log how
often you do any activity and watch it add up — entries, counts, and streaks.
Multi-user from day one; UI strings centralized for i18n.

Stack: FastAPI + uv + Uvicorn. Tailwind CSS v4 + HTMX + vanilla JS (web),
Hyperview/HXML (mobile), SQLite.
Hosting: Ubuntu 24.04 (production via Caddy + systemd).

## Current state

- Live at: https://mushin.aqnas.xyz
- Local dev: `./run.sh` (port 8000)
- Repo: github.com/yjaquinas/mushin
- Production path: `/opt/mushin/mushin/` on `aqnas-prod`
- Production port: 8013

## Domain model

One level: activity → entry.

Architecture: one FastAPI backend, two hypermedia renderers — HTMX (web/PWA)
and HXML (Hyperview native) — over a shared renderer-agnostic domain/service
layer. Online-first.

## Deployment

Push to `main` triggers `.github/workflows/deploy.yml`, which SSHes into
the production host and runs `deploy/run.sh` in this repo. See the studio's
`deploy-procedure` skill for the full model.

`deploy/run.sh` handles: git sync (`git fetch + reset --hard`),
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
