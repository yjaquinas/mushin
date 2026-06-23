---
name: color-system
description: Mushin's color palette as renderer-agnostic tokens that map to both Tailwind utilities (web) and HXML style attributes (future native). Use when styling any surface, picking a color, or defining a new token.
---

# Mushin color system

Single source of truth lives in `app/static/src/input.css` (`@theme` block =
light values, `[data-theme="dark"]` block = dark overrides, same token
names). This skill is the lookup reference + binding rules; for *why* a
specific value was chosen, the contrast math is commented inline in
`input.css` next to that token — read there first, this file second.

## Principles (binding)

- **One token source, renderer-agnostic.** Define each token once; it maps
  to *both* Tailwind v4 utilities (web) and HXML style attributes (future
  native). Never maintain two palettes.
- Restraint over decoration — the 무심/無心 brand is quiet. No hype
  gradients, no glow.
- **Never encode meaning in color alone** (chips, status, heatmap bars):
  pair color with shape/weight/height + a glyph where applicable —
  colorblind and bright-sun safe.
- Non-text fills/borders/icons/focus-rings need **3:1** contrast minimum;
  body-size text needs **4.5:1**. Every token below is tagged with which
  bar it has to clear.

## Foreground/background pairing rule (binding)

`--color-brand`, `--color-obsidian`, and `--color-surface-*` are
**background-only roles** — never use as a `text-*` foreground.

- `--color-brand` / `--color-obsidian` are fixed (never swap with
  `data-theme`). `--color-surface-*` DOES swap.
- A **fixed** background (`bg-brand`, `bg-obsidian`) pairs with
  `text-on-brand` only. A **swapping** surface (`bg-surface-0/1/2`) pairs
  with the swapping `text-text-primary/secondary/muted` tokens. Mixing a
  fixed background with a swapping foreground (or vice versa) converges
  the two to the same value in one theme and the element disappears — this
  bug class was found 2026-06-22 (10 instances), see `git log` on
  `input.css` for the fix commit if you need the history.
- Before adding any new `bg-*`/`text-*` pairing: does the background swap
  with `data-theme`? If yes, foreground must swap too. If no (fixed),
  foreground must be a token built for that fixed background
  (`text-on-brand`).

## Current token table

| Token | Light | Dark | Bar | Notes |
|---|---|---|---|---|
| `--color-brand` | `#0F172A` | `#5A6B85` | bg only | app name, primary CTA, hero numeral background pairing. Dark value is 2.70:1 on `surface-1` (cards) — documented shortfall, graded against the canvas case (3.30:1 on `surface-0`) instead. |
| `--color-obsidian` | `#0F172A` fixed | same | bg only | never swaps — masthead/brand-glyph moments only |
| `--color-cinnabar` | `#E34234` fixed | same | bg/fill | never swaps — same fixed-brand-moment use as obsidian |
| `--color-on-brand` | `#ffffff` | `#f0eeec` | text, 4.5:1 | pairs with fixed `bg-brand`/`bg-obsidian` only |
| `--color-surface-0` | `#F8FAFC` | `#0F172A` | bg | canvas |
| `--color-surface-1` | `#FFFFFF` | `#1E293B` | bg | card / sheet |
| `--color-surface-2` | `#F1F5F9` | `#2A3950` | bg | inset / pressed |
| `--color-border` | `#E2E8F0` | `#334155` | non-text | card outlines, dividers, chip outlines |
| `--color-border-strong` | `#7C8AA0` | `#73839A` | non-text, 3:1 | clears 3:1 vs `surface-1` both themes (3.50 / 3.79). Used for `.cal-day--today` ring, focus-ring fallback, `--color-heatmap-baseline` alias |
| `--color-text-primary` | `#0F172A` | `#F8FAFC` | text, 4.5:1 | body copy, labels |
| `--color-text-secondary` | `#475569` | `#94A3B8` | text, 4.5:1 | demoted labels |
| `--color-text-muted` | `#64748B` | `#96A2B4` | text, 4.5:1 | captions, placeholders, disabled |
| `--color-accent` | `#E34234` | `#FF6B5B` | non-text, 3:1 | cinnabar. Max ~4.1:1 on light surfaces — **never body text on light**. Chip-selected border/fill, progress-bar fill, focus ring, marked-day dot, `--color-heatmap-bar` alias |
| `--color-accent-subtle` | `#FBE7E4` | `#3A2422` | bg | tint under accent-text (light) / under light text (dark) |
| `--color-accent-text` | `#982015` | `#FF6B5B` | text, 4.5:1 | darkened-cinnabar variant for accent-hued body text on light; dark `accent` already clears 4.5:1 so no separate value needed |
| `--color-danger` | `#A6471C` | `#E8855E` | non-text, 3:1 | account deletion / irreversible actions only. Re-hued off cinnabar (~20° hue separation) so the two don't read as the same red |
| `--color-danger-subtle` | `#FBEAE3` | `#3D2A20` | bg | tint counterpart |
| `--color-heatmap-bar` | `#E34234` | `#FF6B5B` | non-text, 3:1 | = `--color-accent` (duplicated value, not a `var()` reference — see below). Fill for a non-zero day on the activity-detail trend strip |
| `--color-heatmap-baseline` | `#7C8AA0` | `#73839A` | non-text, 3:1 | = `--color-border-strong` (duplicated value). Muted floor/zero-day sliver on the trend strip |

Two fixed, non-swapping tokens (`--color-obsidian`, `--color-cinnabar`) are
never overridden in the dark block — deliberate brand moments only, never
a substitute for swapping `surface`/`accent` roles in ordinary UI.

## Heatmap trend strip (current — added 2026-06-23)

The activity-detail summary card shows 84 trailing days as a row of
height-encoded bars — a non-interactive trend strip. Intensity is encoded
by **bar height**, not by a graded color ramp: a single fill
(`--color-heatmap-bar`) for any non-zero day, and a muted floor
(`--color-heatmap-baseline`) so a zero day is still a visible tick, never
literally blank. This survives grayscale/colorblindness without a
multi-step hue/lightness progression.

Both tokens are deliberate **duplicated-value aliases** of existing tokens
(`accent` and `border-strong` respectively) — written as their own
`--color-heatmap-*` custom properties in `input.css`, not a live `var()`
binding — so they don't silently drift if `accent`/`border-strong` is
retuned later for an unrelated reason. If either source token's value
changes, re-check whether the heatmap tokens should follow.

A prior year-view heatmap calendar used a 5-step graded ramp
(`--color-heat-0` through `--color-heat-4`, `.heat-cell--0..4`). **That
ramp and its classes were removed** (commit `41bdead`, 2026-06-22, the
calendar-persist change that dropped year view) and **must not be
reintroduced** — the current trend strip is a deliberately different,
simpler approach (height + single fill, not a color ramp), not a gap to
fill back in.

## Dark mode

Single activation path: `[data-theme="dark"]`, explicit user choice only
(cookie/toggle) — no `prefers-color-scheme` detection. Default on first
visit (no cookie) is always light. Same token *names* as light, only
values change, so the Tailwind mapping (web) and future HXML mapping
(native) share one contract.

When adding a new token, define it in both the light `@theme` block and
the dark override block in the same `input.css` edit — never let a token
exist in only one theme (it silently falls back to the light value under
`data-theme="dark"`, which is how the `--color-brand` dark-mode-CTA bug
happened, see `git log -- app/static/src/input.css`).

## Type scale, weights, radius, spacing

Also defined in `input.css` (`@theme` block, not yet broken out into a
separate skill). Quick pointers:

- `--font-size-hero-numeral` (48px) is the one-numeral-per-card rule's
  type-scale anchor; `--font-size-title` / `-body` / `-caption` / `-micro`
  step down from there.
- `--font-weight-normal/medium/semibold` — chips use weight (not color
  alone) to signal selected state.
- `--radius-chip-selected` (pill) vs `--radius-chip-unselected` (6px) —
  shape carries selected-state meaning alongside weight + the `✓` glyph.
- `--spacing-tap` (44px) — minimum tap target, WCAG 2.5.5.

See `component-patterns` skill for how these compose into actual
components (chips, cards, calendar days).
