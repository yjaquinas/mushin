---
name: clean-up
description: Use this skill when cleaning up Mushin templates, icons, routes, helpers, or dead code. It captures the project's SVG icon rules, Jinja shared-utility rules, file-size extraction heuristics, and deletion-first cleanup expectations from AGENTS.md.
---

# Clean-up

Apply these rules whenever the task is primarily codebase cleanup, refactoring,
template extraction, icon work, or dead-code removal in Mushin.

## SVG icons

- Keep each icon as its own file at `app/static/icons/{name}.svg`.
- Icon files must contain a complete `<svg>` element with:
  - `width="20"` and `height="20"` as defaults
  - `stroke="currentColor"`
  - `aria-hidden="true"`
- Never inline SVG markup in templates.
- In templates, use the shared Jinja global directly:

```jinja2
{{ icon("pencil", size=16) }}
{{ icon("plus") }}
```

- Do not import `icon` from a template file.
- `icon()` is registered in `app/routes/web/_shared.py` and unknown icon names
  fall back to `circle-dot.svg`.
- When adding a new icon, use Lucide outline path data with:
  - `viewBox="0 0 24 24"`
  - `stroke-width="2"`

Use this exact file shape:

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  ...
</svg>
```

Never:

- Inline `<svg>` in templates
- Use `{% from "components/_icon.html.jinja2" import icon %}`
- Add color attributes other than `stroke="currentColor"` to icon files

## Code hygiene

- Treat 150 lines as the hard ceiling for route files under `app/routes/**/*.py`.
- Treat 150 lines as a strong refactor signal for templates, services, and
  helpers.

When a file grows too large:

- Route files: move handler bodies into a nearby `_<group>_handlers.py`
  companion with no `APIRouter`; keep the route file focused on declarations.
- Templates: extract repeated or standalone sections into
  `components/_<name>.html.jinja2` partials and include them with:

```jinja2
{% include "components/_<name>.html.jinja2" with context %}
```

- Services/helpers: extract cohesive sub-concerns into sibling modules.

## Jinja and shared template utilities

- Before writing Jinja that already exists elsewhere, extract it to a partial.
- Any block repeated in two or more places should become a partial.
- Private partials that are not direct HTMX swap targets should use an
  underscore prefix, such as `_log_form_body.html.jinja2`.
- If a template contains inline `<script>` code, refactor it into a separate
  `.js` file instead of leaving JavaScript in the template.
- Never use `{% from "..." import ... %}` for project-wide utilities.
- Register shared globals once in `app/routes/web/_shared.py`.
- Current project-wide Jinja globals are `strings` and `icon`.
- There must be exactly one `Jinja2Templates` instance for the whole app,
  created in `app/routes/web/_shared.py`.
- `app/routes/public/_contexts.py` re-exports that shared instance; do not make
  another one elsewhere.
- Shared context processors, globals (`strings`, `icon`), and filters
  (`format_entry_time`, `format_count`, `streak_days`) are registered once in
  `_shared.py`. Any surface that needs templates should import the shared
  instance.

## Reuse and extraction

- If the same logic appears in two route handlers or two context builders,
  extract it into a shared helper in the nearest `_` companion module.
- Prefer extraction over duplication before adding more branching or copy-paste.

## Dead code

Delete dead code instead of preserving it with comments.

- Delete unused route files whose `APIRouter` is never included.
- Delete unused templates that are never referenced by `TemplateResponse`,
  `{% extends %}`, or `{% include %}`.
- Remove unused functions and imports.
- Delete empty stubs that only say routes should be registered there.
