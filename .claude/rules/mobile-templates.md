---
paths:
  - "app/templates/mobile/**"
  - "mobile-client/**"
---

# Mobile template conventions

Path-scoped: loads when Claude is editing Hyperview templates or the mobile-client shell. Fill in project-specific additions as conventions settle.

## Template extension and layout

- Hyperview templates use `.hxml.jinja2`.
- Files live in `app/templates/mobile/` (full screens). Shared mobile fragments can go in `app/templates/components/` with the `.hxml.jinja2` extension.
- Every full screen is wrapped in `<doc xmlns="https://hyperview.org/hyperview">` → `<screen>` → `<styles>` + `<body>`.

## Route conventions

- All mobile endpoints live under `/m/` in `app/routes/mobile.py`.
- Responses use `Content-Type: application/vnd.hyperview+xml` — pass `media_type="application/vnd.hyperview+xml"` to `TemplateResponse`. Without it, the client silently ignores the response.
- Full-screen handlers return `<doc>`-wrapped documents. Fragment handlers (for `replace-inner`, `append`, `prepend` actions) return children only, no `<doc>` wrapper.

## Styling

- Styles defined per-screen inside `<styles>` and referenced by `id` via the `style="..."` attribute. Not CSS, not inline.
- Multiple styles compose: `style="heading heading-large"`.
- Use the project's color/typography skill (if defined) for palette and type scale tokens — never hardcode hex values that duplicate what's in a skill.

## Behaviors

- Interactions attach via `<behavior trigger="..." action="..." href="..." />` as children of the interactive element.
- Common triggers: `press`, `longPress`, `visible`, `refresh`, `load`.
- Common actions: `navigate`, `back`, `replace`, `replace-inner`, `append`, `prepend`, `reload`, `dispatch-event`.
- Forms submit via a `<behavior>` with `verb="post"` (or `put`/`delete`) — default is GET which won't send form data.

## Mobile-client shell

- `mobile-client/` is a thin React Native + Expo shell that loads an initial HXML URL.
- Do not add screen-level JavaScript logic — mobile is server-driven. If a feature needs client logic, it likely doesn't belong on mobile yet.

## Project-specific additions

_(Add project-specific mobile conventions here — navigation stacks, modal patterns, etc.)_
