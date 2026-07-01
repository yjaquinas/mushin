# mushin — Claude instructions

## What this project is

Mushin (무심, 無心 — "no-mind") is a general personal progress tracker. Log how
often you do any activity and watch it add up — entries, counts, and streaks.
Multi-user from day one; UI strings centralized for i18n.

Stack: FastAPI + uv + Uvicorn. Tailwind CSS v4 + HTMX + vanilla JS (web),
Hyperview/HXML (mobile), SQLite.
Hosting: Ubuntu 24.04 (production via Caddy + systemd).

## Domain model

One level: activity → entry.

Architecture: one FastAPI backend, two hypermedia renderers — HTMX (web/PWA)
and HXML (Hyperview native) — over a shared renderer-agnostic domain/service
layer. Online-first.
