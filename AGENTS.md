# mushin — Codex instructions

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

## Auth, visibility, and data isolation

Every user must sign up with a username and password before doing anything.
Username is load-bearing: every activity lives at `/@{username}/{slug}`, so a
username-less account cannot participate in the core URL scheme.

Visibility has three tiers:

- `public` — the whole record, including notes, is visible to anyone.
- `private` — visitors can see the character sheet at `/@{username}`: activity
  names, counts, and non-clickable cards. They cannot open
  `/@{username}/{slug}`; that must 303-redirect to `/@{username}`.
- Fellows — accepted mutual connections after sharing consent — can see the
  full record, including entries and free-text notes, on either account.

Private accounts are still searchable by username/display name. Activity names
are visible to any searcher.

`app/services/profiles.py::viewer_capability` and `can_view_activity_detail`
are the single fail-closed authorities for visibility decisions.

- Never inline a `visibility` field comparison in a route handler.
- Never cache a capability result; always call the service function.
- Every data query must be scoped by `owner_id`. An unscoped multi-user query
  is a bug regardless of context.

All user-facing copy lives in `app/ui_strings.py`. Do not hardcode strings in
templates; `test_no_hardcoded_copy_in_templates` enforces this. Add new copy to
`ui_strings.py` first.

## Design tokens

The design-token source of truth is `app/static/src/input.css`. Token names are
semantic roles, not raw color names, so any renderer can consume the same names
without creating a second palette.

Role families defined in `@theme`:

- `brand`, `brand-subtle`, `on-brand` — studio ink and text/icon color on top.
  These swap with theme like other role tokens.
- `surface-0`, `surface-1`, `surface-2` — background layers.
- `text-primary`, `text-secondary`, `text-muted` — text emphasis tiers.
- `border`, `border-strong` — dividers and outlines.
- `accent`, `accent-subtle`, `accent-text` — brand color, pale tint, and
  text-safe darker variant.
- `level`, `level-subtle` — progression/success color.
- `danger`, `danger-subtle` — destructive-action color.
- `heat-0` through `heat-4` — heatmap intensity ramp.

Light/dark token values must stay synchronized in three places:

1. `@theme { ... }` — light/default values.
2. `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { ... } }`
   — system-dark default when the user has not explicitly chosen light.
3. `[data-theme="dark"] { ... }` — explicit dark theme.

Blocks 2 and 3 must carry identical values for every token. Light is the
default theme; do not flip it without an explicit recorded decision.

`--color-obsidian` and `--color-cinnabar` are fixed-value exceptions declared
once in `@theme` and never overridden in dark-mode blocks. Use them only for
deliberate brand moments, not ordinary UI. `--color-on-brand` is not an
exception; it swaps like other role tokens.

`--color-accent` is not safe for body-size text on light surfaces. Use
`--color-accent-text` for accent-colored text; reserve `accent` for fills,
borders, icons, and focus rings.

Tailwind v4 auto-generates utilities from `--color-*`, `--font-size-*`, and
similar custom properties in `@theme`. Future HXML/native parity should map to
these same token names, never a second hand-maintained palette.

## HTMX

Prefer htmx v2.0.10 for AJAX requests and DOM updates. Fall back to vanilla
JavaScript only when the interaction cannot be expressed with htmx attributes.

## SVG icons

Each icon is a standalone SVG file at `app/static/icons/{name}.svg`. The file
contains a complete `<svg>` element with `width="20" height="20"` as the
default size, `stroke="currentColor"`, and `aria-hidden="true"`. Do not inline
SVG in templates.

`icon()` is a Jinja2 global registered in `app/routes/web/_shared.py`. Call it
directly in templates without importing:

```jinja2
{{ icon("pencil", size=16) }}
{{ icon("plus") }}
```

The helper reads `static/icons/{name}.svg`, substitutes `width` and `height`
for the requested size, and returns safe Markup. Unknown names fall back to
`circle-dot.svg`.

When adding an icon, use Lucide outline path data with `stroke-width="2"` and
`viewBox="0 0 24 24"`, then create `app/static/icons/{name}.svg` with:

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  ...
</svg>
```

Do not:

- Inline `<svg>` directly in templates.
- Use `{% from "components/_icon.html.jinja2" import icon %}`.
- Add color attributes other than `stroke="currentColor"` to icon files.

## Code hygiene

Route files under `app/routes/**/*.py` have a 150-line ceiling. For all other
files, including services, templates, and helpers, 150 lines is still a strong
signal to look for extraction opportunities.

When a file grows past 150 lines:

- Route files: extract handler bodies to a `_<group>_handlers.py` companion
  with no `APIRouter`. The route file keeps only route declarations.
- Templates: extract repeated or standalone sections into
  `components/_<name>.html.jinja2` partials and include them with
  `{% include "components/_<name>.html.jinja2" with context %}`.
- Service/helper files: extract cohesive sub-concerns into sibling modules.

Before writing Jinja2 that already appears elsewhere, extract it to a partial.
A block repeated in two or more places should become a partial. Private partials
that are not direct HTMX swap targets get an underscore prefix, such as
`_log_form_body.html.jinja2` or `_add_activity_form.html.jinja2`.

Never use `{% from "..." import ... %}` for project-wide utilities. Register
them as Jinja2 globals in `app/routes/web/_shared.py`. Current globals are
`strings` and `icon`.

There is exactly one `Jinja2Templates` instance for the whole app, created in
`app/routes/web/_shared.py`. `app/routes/public/_contexts.py` re-exports it.
Never create a second instance elsewhere; context processors, globals, and
filters must stay in sync automatically.

If the same logic appears in two route handlers or two context builders,
extract it into a shared helper function in the nearest `_` companion module.

Remove dead code instead of preserving it with comments:

- Delete unused route files whose `APIRouter` is never included.
- Delete unused templates that are never referenced by `TemplateResponse`,
  `{% extends %}`, or `{% include %}`.
- Remove unused functions and imports.
- Delete empty stubs that only say routes should be registered there.

Shared context processors, globals (`strings`, `icon`), and filters
(`format_entry_time`, `format_count`, `streak_days`) are registered once in
`_shared.py`. Any surface that needs templates imports the shared instance.
