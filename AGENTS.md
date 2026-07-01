# mushin — Codex instructions

## Project

Mushin (무심, 無心, "no-mind") is a multi-user personal progress tracker for
activities, entries, counts, and streaks. UI copy is centralized for i18n.

Stack: FastAPI + uv + Uvicorn, Tailwind CSS v4 + HTMX + vanilla JS (web),
Hyperview/HXML (mobile), SQLite. Hosting: Ubuntu 24.04 via Caddy + systemd.

Model: `activity -> entry`.

Architecture: one FastAPI backend with two hypermedia renderers, HTMX (web/PWA)
and HXML (native), on top of a shared renderer-agnostic service layer.

## Auth, visibility, isolation

Users must sign up with username + password before doing anything. Username is
load-bearing because activities live at `/@{username}/{slug}`.

Visibility:

- `public`: full record, including notes, visible to anyone.
- `private`: `/@{username}` shows activity names, counts, and non-clickable
  cards; `/@{username}/{slug}` must `303` back to `/@{username}`.
- fellows: accepted mutual connections can see the full record, including notes.

Private accounts are still searchable by username/display name, and activity
names remain visible.

`app/services/profiles.py::viewer_capability` and
`can_view_activity_detail` are the only fail-closed visibility authorities.

- Never compare `visibility` directly in route handlers.
- Never cache capability results; always call the service.
- Every query must be scoped by `owner_id`. Any unscoped multi-user query is a
  bug.

All user-facing copy belongs in `app/ui_strings.py`. Do not hardcode template
strings. Add new copy there first; `test_no_hardcoded_copy_in_templates`
enforces this.

## Design tokens

`app/static/src/input.css` is the source of truth. Token names are semantic
roles, not raw colors, so all renderers share one palette.

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

`--color-obsidian` and `--color-cinnabar` are fixed exceptions declared once in
`@theme` and never overridden in dark mode. Use them only for deliberate brand
moments. `--color-on-brand` is not fixed and must still swap by theme.

`--color-accent` is not safe for body text on light surfaces. Use
`--color-accent-text` for accent text; reserve `accent` for fills, borders,
icons, and focus rings.

Tailwind v4 auto-generates utilities from `--color-*`, `--font-size-*`, and
similar theme variables. HXML/native parity should reuse these same token names,
not a second palette.

## HTMX

Prefer htmx v2.0.10 for requests and DOM updates. Use vanilla JavaScript only
when htmx attributes cannot express the interaction. Never inline JavaScript in
templates with `<script>`; put all JavaScript in separate `.js` files.

## SVG icons

Each icon lives at `app/static/icons/{name}.svg` as a full `<svg>` with
`width="20" height="20"`, `stroke="currentColor"`, and `aria-hidden="true"`.
Do not inline SVG in templates.

`icon()` is a Jinja global from `app/routes/web/_shared.py`. Use it directly:

```jinja2
{{ icon("pencil", size=16) }}
{{ icon("plus") }}
```

The helper reads `static/icons/{name}.svg`, swaps `width` and `height`, and
returns safe Markup. Unknown names fall back to `circle-dot.svg`.

New icons should use Lucide outline path data with `stroke-width="2"` and
`viewBox="0 0 24 24"`:

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  ...
</svg>
```

Do not:

- Inline `<svg>` in templates.
- Use `{% from "components/_icon.html.jinja2" import icon %}`.
- Add color attributes other than `stroke="currentColor"` to icon files.

## Code hygiene

`app/routes/**/*.py` has a hard 150-line ceiling. Elsewhere, 150 lines is still
a strong signal to extract.

When a file grows past 150 lines:

- Routes: move handler bodies to a `_<group>_handlers.py` companion with no
  `APIRouter`; keep route files declarative.
- Templates: extract repeated or standalone sections into
  `components/_<name>.html.jinja2` and include with
  `{% include "components/_<name>.html.jinja2" with context %}`.
- Services/helpers: split cohesive sub-concerns into sibling modules.

Before duplicating Jinja, extract a partial. Any block repeated in two or more
places should become a partial. Private partials that are not HTMX swap targets
should use an underscore prefix, for example
`_log_form_body.html.jinja2`.

Never use `{% from "..." import ... %}` for project-wide utilities. Register
globals once in `app/routes/web/_shared.py`; current globals are `strings` and
`icon`.

There must be exactly one `Jinja2Templates` instance, created in
`app/routes/web/_shared.py` and re-exported by `app/routes/public/_contexts.py`.
Do not create another.

If the same logic appears in multiple route handlers or context builders,
extract a shared helper in the nearest `_` companion module.

Delete dead code instead of commenting around it:

- Remove unused route files whose `APIRouter` is never included.
- Remove unused templates not referenced by `TemplateResponse`, `{% extends %}`,
  or `{% include %}`.
- Remove unused functions and imports.
- Remove empty registration stubs.

Context processors, globals (`strings`, `icon`), and filters
(`format_entry_time`, `format_count`, `streak_days`) are registered once in
`_shared.py`. All template surfaces must import the shared instance.
