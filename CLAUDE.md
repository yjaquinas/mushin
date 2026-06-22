# mushin — Claude instructions

## What this project is

Mushin (무심, 無心 — "no-mind") is a general personal progress tracker. Log how
often you do any activity and watch it add up — entries, counts, and streaks,
no levels or grinding. Multi-user from day one; UI strings centralized for
i18n.

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

One level: activity → entry. (`category` survives only as an internal,
automatically-created 1:1 wrapper row behind every activity — never a
separate user-facing concept, never a second creation step.)

- Field-type primitives (the recipe vocabulary): tag-group, scale, count,
  memo, match-list. An activity can mix any combination on one entry
  stream — e.g. a running tag/count/memo log alongside a match-list, all on
  the same activity, all the same entries table.
- An activity's hero stat is always the running count (a monotonic count
  of entries, reported per week/month/year/lifetime). There is no
  progression ladder, level, or gating mechanism — Mushin tracks activity
  and frequency, not tiers.
- No starter templates are seeded on signup. New accounts start with zero
  activities; the home screen shows quick-start suggestions (tap-to-create,
  empty/blank activity, no pre-built recipe) alongside "start from scratch."
  Activity creation is inline on the home screen — no separate creation
  page, no icon picker, name only.
- Tables: user, category (internal, 1:1 with activity), activity, field_def,
  tag, entry, entry_tag, entry_value, match, connection, block, comment.
- Social graph: a **fellow** is a mutual connection (request → accept/decline;
  symmetric). The `connection` table holds the directed handshake plus a
  canonical `user_lo/user_hi` pair (unique, prevents reverse-duplicates);
  `block` is a one-directional silence with a no-existence-oracle guarantee.
  The connection term in all copy is "fellow"; the action verb is always
  "Connect" (never coin "to fellow").

Architecture: one FastAPI backend, two hypermedia renderers — HTMX (web/PWA) and
HXML (Hyperview native) — over a shared renderer-agnostic domain/service layer.
Online-first.

## Auth + accounts

Multi-user from day one. Social login: **Google**, plus **email/password
fallback**. Apple is deferred (revisited at iOS launch). Google scope is
`openid email profile`. Every query scoped by `owner_id`. OAuth client
id/secret are a manual task (Google dev console), stored in
`/opt/mushin/.env` like `SERVER_HOST` / `DEPLOY_KEY`.

**Account required to start (guest mode retired 2026-06-16).** Every new user
must sign up (username + password, or Google OAuth) before logging an entry.
Username is load-bearing infrastructure — every activity lives at
`/@{username}/{slug}` — so a no-username guest account can't participate in
the core shareable-URL feature. Existing guest rows drain via the guest-reaper
timer on their normal 7d/30d schedule; the reaper service keeps running until
the backlog is empty, at which point it will be removed in a separate cleanup
build. The upgrade-in-place flow (`/auth/upgrade`) remains functional during
the drain window.

**Visibility is three-tier (not binary).** `public` = whole record incl. notes
visible to anyone. `private` = a non-connected visitor sees the **character
sheet** at `/@{username}` (activity names + counts, cards not
clickable) but **cannot open `/@{username}/{slug}`** — that 303-redirects to
`/@{username}`. A **fellow** (accepted mutual connection, after a separate
sharing-consent) sees the full record incl. entries and free-text notes on
either account. `private` no longer means "hidden": all accounts are searchable
by username/display name, and a private account's activity *names* are visible
to any searcher. The single fail-closed authority for every visibility decision
is `app/services/profiles.py::viewer_capability` / `can_view_activity_detail` —
never inline a `visibility` check in a handler, never cache a capability.

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
`data_io.py`, `mobile.py`), one file per route group, 300-line ceiling — see
the `route-structure` rule (`.claude/rules/route-structure.md`).

## Reference docs

- `DEVELOPER_GUIDE.md` — full developer reference (architecture, server users,
  deploy flow, database schema, monitoring, break-glass)
- `~/.claude/CLAUDE.md` — studio-wide context, brand, default tech stack
- `~/.claude/skills/` — studio skills (deploy-procedure, port-registry,
  systemd-service, caddy-config, secret-hygiene, etc.)
