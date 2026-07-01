# Code hygiene rules

## File length

**150-line ceiling for route files** (`app/routes/**/*.py`). For all other
files (services, templates, helpers), 150 lines is still a strong signal to
look for extraction opportunities.

When a file grows past 150 lines:

- **Route files** — extract handler bodies to a `_<group>_handlers.py`
  companion (no `APIRouter`). The route file keeps the route declarations
  only; the companion keeps the logic. See `_entries_handlers.py`,
  `_history_context.py` as examples.
- **Template files** — extract repeated or standalone sections into
  `components/_<name>.html.jinja2` partials (underscore prefix = shared
  internal partial), then `{% include "components/_<name>.html.jinja2" with context %}`.
- **Service/helper files** — extract cohesive sub-concerns into sibling
  modules.

## Deduplication

### Templates

Before writing a block of Jinja2 that already appears elsewhere, extract it
to a partial. Rules:

- A block repeated in two or more places → partial.
- Partials that are "private" (not direct HTMX swap targets) get an
  underscore prefix: `_log_form_body.html.jinja2`, `_add_activity_form.html.jinja2`.
- The `{% include "…" with context %}` form passes the full template context
  automatically — no need to repeat variable names.

### Jinja2 globals vs imports

Never use `{% from "…" import … %}` for project-wide utilities. Register
them as Jinja2 globals in `app/routes/web/_shared.py` so every template can
call them without an import line. Current globals: `strings`, `icon`.

### Template instances

There is exactly **one** `Jinja2Templates` instance for the whole app, created
in `app/routes/web/_shared.py`. `app/routes/public/_contexts.py` re-exports it.
Never create a second instance elsewhere — context processors, globals, and
filters must stay in sync automatically.

### Python helpers

If the same logic appears in two route handlers or two context builders,
extract it into a shared helper function in the nearest `_` companion module.
Example: `resolve_history_viewer()` in `_history_context.py`.

## Unused code and files

- **Unused route files**: if a module defines an `APIRouter` that is never
  `include_router`'d in any `__init__.py` or `main.py`, delete it.
- **Unused template files**: if a template is never referenced via
  `TemplateResponse`, `{% extends %}`, or `{% include %}`, delete it.
- **Unused functions/imports**: remove them. Don't leave dead code with a
  comment; the git history is the record.
- **Empty stubs**: files with only a comment saying "register routes here"
  and no actual routes are dead weight — delete them.

## Python: no duplicate template setups

Any shared context processors, globals (`strings`, `icon`), or filters
(`format_entry_time`, `format_count`, `streak_days`) are registered once in
`_shared.py`. Any surface that needs templates imports the shared instance —
it never re-registers these on a new object.
