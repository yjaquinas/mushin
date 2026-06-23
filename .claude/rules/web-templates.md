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
- **`base.html.jinja2`'s shell is a sticky-footer flex column: `<body>` is `flex flex-col min-h-screen`, `<main>` is the sole `grow` child, and `<footer>` is flow-positioned (never `fixed`/`sticky`) so it pins to the bottom on short pages but is pushed down naturally by long ones — don't add a second `grow`/`flex-1` child or convert the footer to fixed positioning.**

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
- Quick-add / "log" return HTMX fragments that swap without full reload.
- One hero numeral per activity card. Tags are entered as inline `#hashtags` inside the free-text notes field (`components/tag_group.html.jinja2`), not as separate tap-select chips — there is no per-tag checkbox/chip affordance to keep ≥44px or visually distinguish by selected state.
- The no-account entry path uses **"No account needed — it's your own record from the start"** framing — never claim "nothing leaves your device" (guest data is on the server).
- Never hardcode user-facing copy — pull from the centralized strings module (see `copy-patterns`).
- Public, unauthenticated routes (`/@{username}`, `/@{username}/{activity-slug}`) render through a dedicated read-only template set (`web/public_profile.html.jinja2`, `web/public_activity.html.jinja2`) when the viewer isn't the owner. Never reuse a top-level `web/` owner-dashboard *page* template for these routes.
- Shared `components/` partials (e.g. the calendar/history view — `components/history.html.jinja2`, `components/day_entries.html.jinja2`, `components/period_log.html.jinja2`) ARE the sanctioned sharing unit between the owner dashboard and the read-only visitor pages: both `web/activity_detail.html.jinja2` and `web/public_activity.html.jinja2` may `{% include %}` the same partial. The safety boundary for a shared partial is the **route's context shape, not the template's `{% if %}`s** — a read-only route must omit every write-action context key (entry edit/delete URLs, log-new-entry trigger, etc.) entirely rather than passing it as falsy, so a template bug can never render a working write control for a no-session visitor. The underlying mutation routes stay independently `owner_id`-scoped as defense in depth, unchanged by this rule.
- Any fragment swapped via `hx-swap="outerHTML"` must carry forward the id
  it replaces on its own root element (e.g. `id="{{ dom_id }}"`), including
  when it renders empty or branches on a context variable like `action`.
  Two separate fragments lost their stable id this way in one session
  (`fellows_section.html.jinja2` when rendering empty,
  `sharing_consent_confirm.html.jinja2` missing the id outright) — once the
  id vanishes, every later swap targeting it silently aborts with no visible
  error.
