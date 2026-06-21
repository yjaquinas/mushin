---
name: component-patterns
description: Mushin's reusable HTMX/Jinja component patterns — activity card, quick-add sheet, tag chip-group, progress bar/ring, calendar/heatmap. Use when building or reusing a web component. Stub — to be filled by web-renderer/ui-stylist as components land.
---

# Mushin component patterns

> **Status: stub.** Filled by `web-renderer` / `ui-stylist` as components are
> built (Build Plan Phase 1–2). Until then, follow the principles below.

## Principles (binding even while stubbed)

- **Activity card:** one hero numeral + one progress affordance; detailed stats
  live on the detail screen, not the card.
- **Tag chip-group:** chips **wrap** (never horizontal scroll-hide), ≥44px tap
  targets, selected vs unselected differ by **shape/weight + glyph** (not color
  alone). First-use "add tag" is one tap from quick-add.
- **Quick-add / "log":** returns an HTMX **fragment** that swaps in without a
  full reload, and **tag selection survives the swap**.
- **Progress bar/ring:** the reward is one moment of motion on log (the bar
  advancing, a level tick) — keep it quiet, no glow.
- Field rendering follows the **shared domain field-priority order** (hero →
  progress → advance line), never a per-component hierarchy.

## To document here when built

- Each component: markup skeleton, the HTMX attributes it uses, the fragment it
  swaps, and its accessibility notes.

## Social-graph components (to build — fellows, requests, search)

Forward spec for the social-graph build; fill in markup/HTMX details as each lands.

- **Fellows list** — a restrained section *below* the activity cards. Text-only
  rows (`@username` + display name, links to their profile); **no avatars** this
  pass. Names shown to the owner and to mutual fellows; to other visitors show
  only the **count** (never render a private user as a clickable, confirmable
  entity to strangers).
- **Requests cluster** (owner view) — incoming requests with **Accept / Decline**;
  outgoing shown as "Requested" + a quiet **Cancel**. A non-nagging pending
  **count** indicator, content-free.
- **Relationship-state affordance** on others' profiles — Connect / Requested /
  "You're fellows". CTA verb is always "Connect" (see `copy-patterns`).
- **Search panel** — HTMX-debounced input, results grouped **People / Tags**,
  calm empty states. Requires auth; result count capped.
- **All** accept/decline/remove/connect actions are **HTMX fragment swaps** — no
  full page reload; the fellows/requests section is a swappable fragment.

## Heatmap (trailing-365-day grid)

Defined in `app/static/src/input.css`.

- `.heat-cell` — base 10x10px square, `--radius` 2px, background defaults to
  `--color-heat-0`. Apply one of `.heat-cell--0` .. `.heat-cell--4` (mapped
  from bucketed entry count) for the day's intensity.
- **Non-interactive.** 365 cells at this density can't meet the 44px tap
  minimum and aren't meant to be tapped individually. Wrap the whole grid in
  a single `role="img"` element with one descriptive `aria-label` (e.g.
  `"지난 365일 활동 기록"`); individual `.heat-cell` elements are
  `aria-hidden="true"`.
- If a per-day drill-down is needed later, use `.cal-day` (month view) for
  the tappable affordance instead of making heatmap cells interactive.

## Calendar (month view with marked days)

Defined in `app/static/src/input.css`.

- `.cal-day` — base day cell, `≥44px` both axes (`--spacing-tap`),
  centered numeral, `--radius-button` corners. **Interactive** — tapping
  opens that day's entries.
- `.cal-day--marked` — a day with ≥1 entry. Adds `font-weight: semibold`
  AND a small accent dot below the numeral (`::after`). The dot is a
  secondary affordance; the weight change is what survives a colorblind /
  grayscale render.
- `.cal-day--today` — the current day. An inset ring (`box-shadow`,
  `border-strong`) distinguishes it by shape — independent of, and
  combinable with, `.cal-day--marked` and `:focus-visible`.

## Icon system

- **Lucide outline icons**, 24px nominal, rendered at 20px in the card label
  row, inline `<svg stroke="currentColor" fill="none" aria-hidden="true">` via
  a Jinja macro at `app/templates/components/_icon.html.jinja2`.
- Monochrome by inheritance (`currentColor` = `text-text-secondary` in the
  card label row) — never an icon-specific color token.
- Each category stores its own `icon` (Lucide icon name, `category.icon TEXT`,
  nullable). The create-category form offers a fixed picker —
  `categories.ICON_CHOICES` (~10 names: `dumbbell`, `book-open`, `circle-check`,
  `pencil`, `music`, `heart`, `footprints`, `code`, `sprout`, `camera`,
  `circle-dot`). Rows with `icon IS NULL` (pre-migration seed data) fall back to
  `circle-dot`. Icons stay monochrome by inheritance and `aria-hidden="true"` —
  never the sole signal for category identity.
- Icons are `aria-hidden="true"` always — decorative, never the sole signal
  for anything (the category label text carries the meaning).

## Masthead

- The `Mushin 無心` wordmark lives once, in `base.html.jinja2`, above
  `{% block content %}` — not duplicated per-page. `Mushin` in
  `text-title font-semibold text-brand`, `無心` in `text-text-muted`, linking
  to `/home`. Text only, no logo image. The masthead row also holds the
  **theme toggle** (see below) at its right edge — the only other persistent
  chrome on the page, present on every page regardless of auth state.

## Theme toggle

- A single icon-button at the right edge of the masthead row (the slot the
  account menu previously occupied), ≥44px tap target, visible focus ring.
- Cycles **light → dark → system** on tap. Icon reflects current state
  (`sun` / `moon` / `monitor` from the Lucide set via `_icon.html.jinja2`).
  `aria-label` announces both current state and the action ("Theme: system.
  Switch to light.") — pulled from `ui_strings.py`.
- `hx-post /preferences/theme`, `hx-swap="outerHTML"` on itself — returns the
  updated button fragment. Sets a `mushin_theme` cookie (`light` | `dark` |
  `system`).
- Server reads `mushin_theme` on every request and sets `data-theme="light"`
  or `data-theme="dark"` on `<html>` for SSR no-flash. When the cookie is
  `system` or absent, omit `data-theme` and rely on the
  `@media (prefers-color-scheme: dark)` fallback in `input.css`.
- Defined once in `components/theme_toggle.html.jinja2`, included by
  `base.html.jinja2` on every page — no auth context required.

## Delete-my-data dialog (designed, not yet built)

- **Not implemented.** `POST /auth/delete` exists in `app/auth/routes.py` and
  fully cascades the account, but no template currently calls it — there is
  no footer link, no confirm dialog, no entry point anywhere in the UI. The
  string `strings.FOOTER_DELETE_DATA` ("Delete my data") is defined in
  `ui_strings.py` but unused. The original confirm-dialog template
  (`delete_data_dialog.html.jinja2`) was scaffolded once and later removed as
  dead code without the route ever being wired to it.
- Intended design, for whoever builds this next: a quiet text link in the
  footer beside the Privacy Policy link, opening a focus-trapped confirm
  dialog — Alpine-driven open/close, `@click.outside`, `@keydown.escape`,
  focus to the cancel button on open (the **sanctioned Alpine exception**,
  see `web-templates.md`, modeled on `import_data_dialog.html.jinja2`).
  Confirms via `hx-post="/auth/delete"`, `hx-swap="none"`, redirects to `/`
  on success. States the consequence plainly per `copy-patterns` (factual,
  user-initiated — no alarm framing).

## Create-category / adopt card

- "General log" is the default shape for a user-created category: one
  `activity` with `count_mode="running"` and `field_defs = {memo, tag_group}`.
  No field-builder UI in v1.
- Manual create (`/categories/new`): a short form — `name` (required) +
  `icon` picker (`categories.ICON_CHOICES`, default `circle-dot`). Submits to
  `POST /categories`.
- Example adopt cards on the empty-state home post to the **same**
  `POST /categories` endpoint with the example's name/icon prefilled — one
  create path serves both. This is the **first-run** path only; once any
  category exists, the persistent "Add category" row (below) is the
  steady-state path.
- **Persistent "Add category" row**: when `#cards` is non-empty, a
  card-shaped row is pinned as the last child of `#cards` — same width and
  `min-h-tap` as `activity_card`, but visually secondary (dashed/lighter
  border, transparent background, `text-text-secondary`, leading `plus`
  icon, `aria-hidden="true"`). Opens the create-category sheet via
  `hx-get="/categories/new"` into the shared sheet-mount target (see
  "Quick-add / log" sheet pattern — same mount point, only one sheet open at
  a time). On success the new `activity_card` is swapped in via
  `hx-swap="beforeend"` into `#cards`, landing **above** this row, which stays
  anchored at the end. Copy: `strings.HOME_ADD_CATEGORY` ("Add a category").
  The empty-state's three example adopt-cards + "start from scratch" link are
  unchanged and remain the first-run-only treatment (CEO decision: both
  patterns coexist).
- On success, the route returns the new `activity_card` fragment for an HTMX
  swap into `#cards` (or a 303 to `/home` for the no-JS path).

## Empty state

- First-run / zero-category state: the `無心` hanja rendered large
  (`text-hero-numeral`-equivalent size) in `text-text-muted`, paired with
  `strings.APP_GLOSS` and `strings.HOME_EMPTY`, mirroring the entry screen
  pairing. Below that, **three one-tap example category cards**
  (`categories.EXAMPLE_CATEGORIES`: Workout/`dumbbell`, Reading/`book-open`,
  Habits/`circle-check`) — each card is a full-width `hx-post /categories`
  with the example's name + icon prefilled, swapping the returned activity
  card into the list on success. Below the cards, a quiet "or start from
  scratch" text link to `/categories/new`. No illustration assets.

## Log/payoff micro-moment

- CSS-only, triggered by the HTMX `outerHTML` swap of the activity card
  fragment after a log POST:
  - `.hero--bumped` — a one-shot settle on the hero numeral (opacity
    0.6→1, `translateY(2px)`→0, ~280ms ease-out, `animation-fill-mode: none`).
    Applied **only** to the post-log swap fragment, never the initial page
    render — the route passes a `bumped` flag into the card context only from
    the log handler.
  - `.progress-fill` animates its width via `@starting-style` so a swapped-in
    bar fills from its prior value without the route tracking previous state.
  - Level-crossing reuses the existing `.progress-fill--leveled` /
    `level-revert` green-then-fade — the one sanctioned color moment, never
    combined with `.hero--bumped`'s own styling beyond the numeral settle.
  - All of the above wrapped in `@media (prefers-reduced-motion: no-preference)`.
  - No confirmation toast/text — the numeral changing is the feedback.
