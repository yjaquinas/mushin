# Mushin

A general personal progress tracker — log how often you do any activity and watch your level in it rise. A raising-sim RPG of yourself.

Part of the [AQNAS](https://aqnas.xyz) studio. Studio-scope conventions live in `~/.claude/`, which is symlinked to the `claude-config/` folder inside the studio repo (at `$AQNAS_STUDIO_ROOT/claude-config/`, default `~/aqnas-studio/claude-config/`). This file and the files in `.claude/` are project-scope — they override or extend the studio defaults for this project specifically.

## Stack

Inherits the AQNAS defaults from studio-scope: Python 3.12 + uv, FastAPI, HTMX v2 (web), Hyperview/HXML (mobile), SQLite, Tailwind v4, Caddy, systemd. See `~/.claude/CLAUDE.md` for the full list and reasoning.

Project-specific deviations:

_(List any stack choices that differ from studio defaults. If none, delete this section.)_

## Domain

Mushin tracks personal progress across any activity. The model has three levels: category (an activity) → sub-tally → entry. Sub-tallies count in `running` or `progression` (level-track) mode; progression levels gate on time, count, event, or manual rules, with an optional parallel secondary track for prestige tiers. Field-type primitives — tag-group, scale, count, memo, match-list, level+result — are the recipe vocabulary for building a tracker. Multi-user from day one; every query is scoped by `owner_id`. Built for the Korean market with Kakao login first; UI strings centralized for later i18n.

## Agents

Seven Task Force agents live in `.claude/agents/` — they do the building work (as opposed to the C-level agents at studio scope, who deliberate):

- **schema-migrator** — `app/models/`, plain-SQL migrations, db connection, indexes, archive/cascade conventions.
- **domain-engineer** — `app/services/`: counting, streaks, stats, progression math. Renderer-agnostic; no HTTP, no templates.
- **auth-engineer** — `app/auth/`: Kakao + Google OAuth, email/password, guest mode, sessions, `owner_id` scoping helper.
- **web-renderer** — `app/routes/web.py` + `app/templates/web/`: HTMX + Jinja fragments.
- **seed-author** — onboarding template seeding (kendo + reading), including the KKA `level_rule` data.
- **ui-stylist** — Tailwind v4, the renderer-agnostic color/type tokens, `app/static/`.
- **test-engineer** — `tests/`: pytest + Playwright.

A `mobile-renderer` agent (HXML/Hyperview) will be added at Phase 5 (native parity), not before.

## Skills

Project-scope skills live in `.claude/skills/`. Knowledge skills encoding project conventions: **data-model** and **copy-patterns** (created this meeting); **color-system**, **typography**, and **component-patterns** (stubs, filled as the UI lands). Command skills (`fix-issue`, `refactor`) are deferred until there's enough surface to warrant them.

See `.claude/skills/README.md` for the full index.

## Rules

Path-scoped and repo-wide rules live in `.claude/rules/`:

- `python-backend.md` — Python conventions (loads when editing `app/**`)
- `web-templates.md` — HTMX + Tailwind conventions (loads when editing `templates/web/**`)
- `mobile-templates.md` — Hyperview conventions (loads when editing `templates/mobile/**`)
- `tests.md` — pytest + Playwright conventions (loads when editing `tests/**`)
- `repo-wide.md` — always-loaded: secret hygiene, git hygiene, destructive-action caution

## Deploy

- **Domain:** mushin.aqnas.xyz
- **Port:** 8013
- **Production path:** `/opt/mushin/`

See `deploy/` for this project's systemd unit, Caddy config, and bootstrap script. See the `deploy-procedure` skill at studio scope for the full flow.

## Meeting history

Past decisions live in `meetings/`. Each `MEETING-YYYY-MM-DD-{slug}/` captures the deliberation that produced whatever change followed.
