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
  - Sanctioned example: the **delete-my-data confirm dialog**
    (`components/delete_data_dialog.html.jinja2`, triggered from the footer)
    uses Alpine for open/close, focus-trap, and Esc-to-close — this is the
    kind of client-only state Alpine exists for, not a violation of
    HTMX-first.
- No `<script>` tags with inline app logic in templates. Extract to `app/static/js/`.

## Styling

- Tailwind v4 utilities. No custom CSS files except the single entry at `app/static/src/input.css` (Tailwind's `@theme`/`@import` directives, design tokens, and any `@apply` patterns) — compiled by `run.sh`/`deploy/run.sh` to `app/static/style.css`, which is what templates link.
- Class lists should read left-to-right: layout → spacing → color → typography → state modifiers. Long class strings wrap at logical boundaries.
- Do not add arbitrary-value classes (`w-[137px]`) without a reason documented in a comment.

## Accessibility

- Every interactive element has a visible focus state (Tailwind's `focus-visible:` utilities are fine).
- Every form input has a `<label>` (not just a placeholder).
- Every image has `alt` — decorative images use `alt=""` explicitly.
- Heading order makes sense: one `h1` per page, no skipped levels.

## Project-specific additions

- Render fields in the shared field-priority order from the domain layer (hero stat → progress affordance → advance line); don't invent a per-template hierarchy.
- Quick-add / "log" return HTMX fragments that swap without full reload; tag selection survives the swap.
- One hero numeral per activity card; tag chips wrap (never horizontal scroll-hide), ≥44px targets, selected state differs by shape/weight + glyph (not color alone).
- The no-account entry path uses **"No account needed — it's your own record from the start"** framing — never claim "nothing leaves your device" (guest data is on the server).
- Never hardcode user-facing copy — pull from the centralized strings module (see `copy-patterns`).
- Public, unauthenticated routes (`/@{username}`, `/@{username}/{activity-slug}`) render through a dedicated read-only template set (`web/public_profile.html.jinja2`, `web/public_activity.html.jinja2`) when the viewer isn't the owner. Never reuse owner-dashboard templates for these routes — a write affordance (log form, add-category, tag editor) must never be reachable from a no-session visitor, even via a stray `{% if %}`.
