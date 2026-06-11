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
