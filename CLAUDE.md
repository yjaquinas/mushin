# mushin — Claude instructions

## What this project is

Mushin (무심, 無心 — "no-mind") is a general personal progress tracker. Log how
often you do any activity and watch your level in it rise — a raising-sim RPG of
yourself. Multi-user from day one; built for the Korean market with UI strings
centralized for later i18n.

Stack: FastAPI + uv + Uvicorn. Optional Tailwind CSS v4 + Alpine.js + HTMX
(web), Hyperview/HXML (mobile), SQLite.
Hosting: Ubuntu 24.04 (production via Caddy + systemd).
Studio context: see `~/.claude/CLAUDE.md` for studio-wide conventions and brand.

## Current state

- Live at: https://mushin.aqnas.xyz
- Local dev: `./run.sh` (port 8000)
- Repo: github.com/yjaquinas/mushin
- Production path: `/opt/mushin/mushin/` on `aqnas-prod`
- Production port: 8013

## Domain model

Three levels: category (activity) → sub-tally → entry.

- Field-type primitives (the recipe vocabulary): tag-group, scale, count, memo,
  match-list, level + result.
- Count modes per sub-tally: `running`, or `progression` (a level track).
- Progression gating, four kinds: time, count, event, manual. A parallel
  secondary track is supported for prestige tiers.
- Onboarding seeds each account with two starter templates: **kendo**
  (full-featured — running practice, tournament with match-list, time-gated dan
  progression + shōgō track) and **reading** (count-gated progression tiers).
  Cooking, knitting, travel are deferred to a future template gallery.
- Tables: user, category, sub_tally, field_def, tag, entry, entry_tag,
  entry_value, match, level_rule.

Architecture: one FastAPI backend, two hypermedia renderers — HTMX (web/PWA) and
HXML (Hyperview native) — over a shared renderer-agnostic domain/service layer.
Online-first.

## Auth + accounts

Multi-user from day one. Social login: **Kakao + Google**, plus **email/password
fallback**. Naver and Apple are deferred (Apple revisited at iOS launch). Kakao
scope is `profile_nickname` only; Google scope is `openid email profile`. Every
query scoped by `owner_id`. OAuth client id/secret are manual tasks (Kakao +
Google dev consoles), stored in `/opt/mushin/.env` like `SERVER_HOST` /
`DEPLOY_KEY`.

**No-signup guest mode:** users can start with no account via an **anonymous
server account** — a guest `owner_id` behind a device cookie, data in the same
server SQLite (not local/on-device). Created on first interaction (not page
load), templates lazy-seeded on first entry, upgradeable to a real account in
place with zero data migration, and purged by a guest-reaper retention timer if
abandoned. "No signup" is honored; "no server storage" is deliberately **not** —
true local-first was rejected (would fork the domain layer and break native).
The app stays **online-first**: no on-device storage, no offline write queue, no
sync.

## Key constraints

- Every data query is scoped by `owner_id` — multi-user isolation is non-negotiable.
- UI strings stay centralized for later i18n (Korean-only at launch).
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

## Reference docs

- `DEVELOPER_GUIDE.md` — full developer reference (architecture, server users,
  deploy flow, database schema, monitoring, break-glass)
- `~/.claude/CLAUDE.md` — studio-wide context, brand, default tech stack
- `~/.claude/skills/` — studio skills (deploy-procedure, port-registry,
  systemd-service, caddy-config, secret-hygiene, etc.)
