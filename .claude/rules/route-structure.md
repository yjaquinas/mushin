---
paths:
  - app/routes/**/*.py
---

# Route structure

How `app/routes/` is organized. The goal is small, predictable, thin handler
files — never one growing dumping ground.

## Surfaces

The top level of `app/routes/` is divided by *surface*, not by feature:

- `web/` — the HTMX + Jinja web/PWA surface (a directory; see below).
- `public/` — unauthenticated public-profile + tag-search surface (a directory
  if it grows past one route group, a single `public.py` while it stays small).
- `mobile.py` — the Hyperview/HXML native surface.
- `data_io.py` — export/deletion endpoints.

A surface is a directory once it holds more than one route-group file; otherwise
it's a single `<surface>.py`. Don't pre-split a surface that's still one file.

## One file per route group

Inside a surface directory, each file holds exactly one *route group* — a
cohesive set of handlers for one screen or resource (e.g. `web/activities.py`,
`web/entries.py`, `web/fellows/connection.py`). The surface's `__init__.py` is
wiring only (router assembly, shared dependencies) — no handler bodies.

## The 300-line ceiling

No file under `app/routes/` exceeds **300 lines**. When a route-group file
crosses it, resolve in this order — do **not** stop at the first option:

1. **Move business logic into `app/services/`.** Routes are thin: they parse the
   request, call one service function, and render. If a single handler is large
   (the canonical case: the entry-log POST), the fix is almost always that
   domain logic leaked into the handler — relocate it to a service, leaving a
   handler that orchestrates, not computes. This is the *first* thing to try,
   because it fixes the real problem (logic in the wrong layer), not just the
   line count.
2. **Extract remaining handler bodies** into a sibling
   `_<group>_handlers.py` (e.g. `_entries_handlers.py`) when, after step 1, the
   group genuinely has too many distinct thin handlers for one file. The route
   declarations / router registration stay in `<group>.py`; the handler bodies
   move to `_<group>_handlers.py`. The leading underscore marks it as an
   internal companion, not a route group of its own.
3. **Split the route group itself** only if it turns out to be two groups wearing
   one name. Prefer this over a `_handlers.py` file that's also near the ceiling.

Relocating code between two routes files to dodge the ceiling without asking
"does this logic belong in `app/services/`?" is not a fix — it's moving the
problem. Always check layer placement before reaching for option 2 or 3.

## Invariants that don't move with the code

- Every query stays scoped by `owner_id` wherever the handler ends up.
- Visibility decisions stay routed through
  `app/services/profiles.py::viewer_capability` / `can_view_activity_detail` —
  never inlined into a handler, never cached, regardless of which file the
  handler lives in.
