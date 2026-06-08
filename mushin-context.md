# start-new-app context: mushin

Context input for `/start-new-app`. Scaffolds the project, seeds CLAUDE.md and
DEVELOPER_GUIDE.md, and writes the deploy/infra layout. Full execution detail
lives in `mushin-build-plan.md`; this file is the scaffold input only. Adjust
field names to match the command's expected `--context` keys if they differ.

## Project

- slug: mushin
- brand: 무심 (無心, "no-mind")
- description: A general personal progress tracker. Log how often you do any
  activity and watch your level in it rise. A 육성 RPG of yourself.
- repo: github.com/yjaquinas/mushin
- visibility: public
- port: 8013
- subdomain: mushin.aqnas.xyz
- market: Korea
- language: Korean-only (strings centralized for later i18n)

## Stack

Studio default: Python 3.12, uv, FastAPI, HTMX v2, Jinja2 v3, Tailwind v4,
Alpine.js (fallback only), Hyperview/HXML, SQLite, Caddy, systemd.

## Deploy / infra conventions

- `deploy/` vs `infra/` split; canonical `deploy/run.sh` using `git reset --hard` (not pull).
- Caddy conf at `infra/mushin.caddy`, TLS for `mushin.aqnas.xyz`, reverse-proxy to port 8013.
- systemd unit for the app; daily backup folded into the existing rclone job.
- Environments: Mac (`aquinas-mbp`), OrbStack `aqnas-dev`, Oracle `aqnas` (prod, ARM).

## Auth + accounts

Multi-user from day one. Social login: Kakao first (Korean default), Naver
optional, email/password fallback. Every query scoped by `owner_id`. OAuth
client id/secret are manual tasks (Kakao/Naver dev console), stored like
`SERVER_HOST` / `DEPLOY_KEY`.

## Domain model (seed for CLAUDE.md)

Three levels: category (activity) -> sub-tally -> entry.

- Field-type primitives (the recipe vocabulary): tag-group, scale, count, memo,
  match-list, level + result.
- Count modes per sub-tally: `running`, or `progression` (a level track).
- Progression gating, four kinds: time, count, event, manual. A parallel
  secondary track is supported for prestige tiers.
- Onboarding seeds each account with starter templates: kumdo (full-featured),
  plus reading, cooking, knitting, travel (lighter).
- Tables: user, category, sub_tally, field_def, tag, entry, entry_tag,
  entry_value, match, level_rule. Columns in build plan Section 3.

## Architecture note

One FastAPI backend, two hypermedia renderers: HTMX (web/PWA) and HXML
(Hyperview native), over a shared renderer-agnostic domain/service layer.
Online-first.

## Phase 0 target (what the scaffold builds toward)

Scaffold + accounts: project structure, multi-user auth with Kakao login,
account creation, onboarding that seeds starter templates, migrations for all
tables, Korean UI scaffolding.

## Still-open decisions (carry into 1-MANUAL-TASKS.md)

- Login providers beyond Kakao (Naver, Apple, email?).
- Keep 무심 given the everyday "indifferent" connotation, or reconsider.
- Starter-template set and richness.
- Seed kumdo `level_rule` with 대한검도회 (KKA) values (short research pass).
