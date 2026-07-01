# mushin — Codex instructions

## Project

Mushin (무심, 無心, "no-mind") is a multi-user personal progress tracker for
activities, entries, counts, and streaks. UI copy is centralized for i18n.

Stack: FastAPI + uv + Uvicorn, Tailwind CSS v4 + HTMX + vanilla JS (web),
Hyperview/HXML (mobile), SQLite. Hosting: Ubuntu 24.04 via Caddy + systemd.

Model: `activity -> entry`.

Architecture: one backend with web and native hypermedia surfaces on a shared
service layer.

## Auth, visibility, isolation

Authentication is required before using the product. Usernames are
load-bearing and must be treated as stable public identifiers.

Visibility:

- `public`: full record, including notes, visible to anyone.
- `private`: `/@{username}` shows activity names, counts, and non-clickable
  cards; `/@{username}/{slug}` must `303` back to `/@{username}`.
- fellows: accepted mutual connections can see the full record, including notes.

Private accounts may still be discoverable by identity and activity names.

- Never compare `visibility` directly in route handlers.
- Never cache capability results; always call the service.
- Every query must be scoped by `owner_id`. Any unscoped multi-user query is a
  bug.

All user-facing copy must be centralized. Do not hardcode template strings.

## Design tokens

Design tokens are the source of truth. Token names must be semantic roles, not
raw colors, so all renderers share one palette.

Role families in `@theme`:

- `brand`, `brand-subtle`, `on-brand`
- `surface-0`, `surface-1`, `surface-2`
- `text-primary`, `text-secondary`, `text-muted`
- `border`, `border-strong`
- `accent`, `accent-subtle`, `accent-text`
- `level`, `level-subtle`
- `danger`, `danger-subtle`
- `heat-0` through `heat-4`

Keep light/dark token values synchronized in:

1. `@theme { ... }`
2. `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { ... } }`
3. `[data-theme="dark"] { ... }`

Blocks 2 and 3 must stay identical. Light is the default theme unless a
recorded decision says otherwise.

Accent and brand tokens should be used by role, not by visual convenience.
All surfaces should reuse the same token names rather than maintaining a second
palette.

## HTMX

Prefer HTMX for requests and DOM updates. Use vanilla JavaScript only when HTMX
cannot express the interaction. Never inline JavaScript in templates.

## Code hygiene

Route files have a hard 150-line ceiling. Elsewhere, 150 lines is still a
strong signal to extract.

When a file grows past 150 lines:

- Routes: move handler bodies to a `_<group>_handlers.py` companion with no
  `APIRouter`; keep route files declarative.
- Templates: extract repeated or standalone sections into
  `components/_<name>.html.jinja2`.
- Services/helpers: split cohesive sub-concerns into sibling modules.

Before duplicating Jinja, extract a partial. Any block repeated in two or more
places should become a partial. Private partials that are not HTMX swap targets
should use an underscore prefix.

Register project-wide template utilities once and share them across all
template surfaces. There must be exactly one template environment instance.

If the same logic appears in multiple route handlers or context builders,
extract a shared helper in the nearest `_` companion module.

SVG icons should live as standalone files and be rendered through shared
template utilities. Do not inline SVG in templates. Keep icon styling
consistent and based on `currentColor`.

Context processors, globals, and filters must be registered once and reused by
every template surface.
