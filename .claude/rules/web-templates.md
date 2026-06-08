---
paths:
  - "app/templates/web/**"
  - "app/templates/components/**"
  - "app/static/**"
---

# Web template conventions

Path-scoped: loads when Claude is editing HTMX templates, shared components, or static assets. Fill in project-specific additions as conventions settle.

## Template extension and layout

- HTMX templates use `.html.jinja2` (not bare `.html` or `.j2`).
- Files live in `app/templates/web/` (full pages) and `app/templates/components/` (shared fragments).
- Every full page extends `base.html.jinja2` from `app/templates/web/`.

## Interaction model

- **HTMX v2 first.** Use `hx-get`, `hx-post`, `hx-swap`, `hx-trigger` for any interaction that touches the server.
- Full pages render on initial navigation; fragments swap on interaction. Routes detect context via the `HX-Request` header and render either accordingly.
- **Alpine.js only as a fallback** for client-only state that HTMX can't handle cleanly (open/close toggles, client-side validation hints). Prefer HTMX when both would work.
- No `<script>` tags with inline app logic in templates. Extract to `app/static/js/`.

## Styling

- Tailwind v4 utilities. No custom CSS files except the single entry at `app/static/css/app.css` for Tailwind's `@tailwind` directives and any `@apply` patterns.
- Class lists should read left-to-right: layout → spacing → color → typography → state modifiers. Long class strings wrap at logical boundaries.
- Do not add arbitrary-value classes (`w-[137px]`) without a reason documented in a comment.

## Accessibility

- Every interactive element has a visible focus state (Tailwind's `focus-visible:` utilities are fine).
- Every form input has a `<label>` (not just a placeholder).
- Every image has `alt` — decorative images use `alt=""` explicitly.
- Heading order makes sense: one `h1` per page, no skipped levels.

## Project-specific additions

_(Add project-specific UI conventions here — brand tokens, header/footer structure, etc.)_
