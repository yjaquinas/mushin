# SVG icon system

## Where icons live

Each icon is a standalone SVG file at `app/static/icons/{name}.svg`. The file
contains a complete `<svg>` element with `width="20" height="20"` as the
default size, `stroke="currentColor"`, and `aria-hidden="true"`. No inline
SVG in templates.

## How to use in templates

`icon()` is a Jinja2 global (registered in `app/routes/web/_shared.py`) —
call it directly anywhere in any template without importing:

```jinja2
{{ icon("pencil", size=16) }}
{{ icon("plus") }}          {# defaults to size=20 #}
```

The function reads the matching `static/icons/{name}.svg`, substitutes the
`width`/`height` attributes for the requested size, and returns safe Markup.
Unknown names fall back to `circle-dot.svg`.

## Adding a new icon

1. Grab the Lucide outline path data (`stroke-width="2"`, `viewBox="0 0 24 24"`).
2. Create `app/static/icons/{name}.svg` with this template:

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  ...inner path/circle/line elements...
</svg>
```

3. Use `{{ icon("{name}", size=N) }}` in any template — no import needed.

## Do NOT

- Inline `<svg>` directly in templates.
- Use `{% from "components/_icon.html.jinja2" import icon %}` (that file was
  deleted; the global supersedes it).
- Add color attributes (`fill`, `stroke` values other than `currentColor`) to
  icon SVG files — icons inherit color from their CSS context.
