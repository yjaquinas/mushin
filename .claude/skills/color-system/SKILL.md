---
name: color-system
description: Mushin's color palette as renderer-agnostic tokens that map to both Tailwind utilities (web) and HXML style attributes (future native). Use when styling any surface, picking a color, or defining a new token. Stub — to be filled by ui-stylist as the UI lands.
---

# Mushin color system

> **Status: stub.** Filled by `ui-stylist` as the UI is built (Build Plan
> Phase 1–2). Until then, follow the principles below.

## Principles (binding even while stubbed)

- **One token source, renderer-agnostic.** Define the palette once as named
  tokens that map to *both* Tailwind v4 utilities (web) and HXML style attributes
  (future native). **Never maintain two palettes** — when native parity lands it
  consumes the same tokens.
- Restraint over decoration — the 무심/無心 brand is quiet. No hype gradients or
  glow.
- **Never encode meaning in color alone** (chips, status): pair color with
  shape/weight + a glyph for colorblind and bright-sun legibility.
- Ensure sufficient contrast on the home-card hero numeral and on chips.

## To define here when built

- The named palette (brand, surface, text, accent, success/level-up, muted).
- Token → Tailwind utility mapping and token → HXML attribute mapping.
- Usage rules (what each token is for; what not to use it for).

## Heatmap intensity ramp

Defined in `app/static/src/input.css`. Five steps, `--color-heat-0` through
`--color-heat-4`, monotonically increasing in lightness/saturation from
`surface-2` toward `accent` — colorblind-tolerant (lightness alone signals
intensity, not hue). `heat-0` equals `surface-2` exactly, so an empty cell
reads as "inset/empty," never as a card background. `heat-4` equals `accent`.

| Token         | Value     | Meaning                  |
|---------------|-----------|--------------------------|
| `--color-heat-0` | `#eeece9` | zero entries (= surface-2) |
| `--color-heat-1` | `#d6e0ec` | low activity             |
| `--color-heat-2` | `#aec4dc` | moderate activity        |
| `--color-heat-3` | `#6f93b9` | high activity            |
| `--color-heat-4` | `#2e5b8a` | busiest day(s) (= accent)|

Bucket the entry count into 5 bins server-side and apply `.heat-cell--0`
through `.heat-cell--4`.

## Dark mode tokens

Defined in `app/static/src/input.css` under `[data-theme="dark"]` (explicit
choice) and mirrored under `@media (prefers-color-scheme: dark)` (system
default, no cookie set). Same token *names* as light — only values change, so
both renderers keep one token contract.

Tokens requiring a dark variant: `surface-0/1/2`, `text-primary/secondary/
muted`, `border` / `border-strong`, `accent` / `accent-subtle`, `level` /
`level-subtle`, `danger` / `danger-subtle`, and the full `heat-0..4` ramp.

Invariants that must hold in dark too:
- `heat-0 == surface-2` (empty cell reads as inset, not background).
- `heat-4 == accent`.
- The heat ramp is re-derived against the dark surfaces, not a naive
  darken of the light ramp.
- `accent-subtle` / `level-subtle` are light tints under dark text in light
  mode; in dark mode they need their own (dark) tint under light text —
  don't just invert. Re-check the chip-selected and level-up contrast pairs.
- The focus ring (`outline: 2px solid var(--color-accent)`) must clear WCAG
  non-text contrast (3:1) against both dark and light canvases.

### Token values: light vs dark

| Token                   | Light     | Dark      | Notes |
|-------------------------|-----------|-----------|-------|
| `--color-surface-0`     | `#f7f6f4` | `#1c1b1a` | canvas |
| `--color-surface-1`     | `#ffffff` | `#262524` | card / sheet |
| `--color-surface-2`     | `#eeece9` | `#322f2d` | inset / pressed; = heat-0 |
| `--color-border`        | `#dedad5` | `#3d3a37` | |
| `--color-border-strong` | `#b8b2aa` | `#5c5751` | |
| `--color-text-primary`  | `#1a1a1a` | `#f0eeec` | |
| `--color-text-secondary`| `#5c5751` | `#b8b2aa` | |
| `--color-text-muted`    | `#9e9790` | `#7d766f` | |
| `--color-accent`        | `#2e5b8a` | `#7ba3cc` | lightened ink-blue; ≥3:1 on dark surface-0/1 for focus ring; = heat-4 |
| `--color-accent-subtle` | `#e8eef5` | `#2a3a4d` | light: pale tint under dark text. dark: dark desaturated tint under light text (chip-selected bg) |
| `--color-level`         | `#2a7a4b` | `#5fae80` | lightened green, legible on dark surfaces |
| `--color-level-subtle`  | `#e6f4ec` | `#1f3a2a` | dark tint counterpart |
| `--color-danger`        | `#b03a2e` | `#e08a7d` | lightened for dark legibility (no component yet, account-delete) |
| `--color-danger-subtle` | `#fbeae8` | `#3d2420` | dark tint counterpart |
| `--color-heat-0`        | `#eeece9` | `#322f2d` | = surface-2 |
| `--color-heat-1`        | `#d6e0ec` | `#3a4350` | |
| `--color-heat-2`        | `#aec4dc` | `#4a5c70` | |
| `--color-heat-3`        | `#6f93b9` | `#5f7f9c` | |
| `--color-heat-4`        | `#2e5b8a` | `#7ba3cc` | = accent |

Dark ramp is re-derived from dark surface-2 toward dark accent (not a naive
darken of the light ramp) — each step increases lightness/saturation
monotonically (contrast ratios between adjacent steps: 1.33, 1.46, 1.64,
1.59), preserving the colorblind-safe lightness progression.

Contrast checks (WCAG):
- Dark `text-primary` on `surface-0`: 14.86:1. `text-secondary` on
  `surface-1`: 7.28:1. `text-muted` on `surface-0`: 3.84:1.
- Dark `accent` on `surface-0`: 6.51:1; on `surface-1`: 5.79:1 — both clear
  the 3:1 non-text minimum for the global focus ring.
- `.chip--selected` (accent-subtle bg + accent text/border) in dark: 4.39:1.
- Dark `level` on `surface-1`: 5.72:1. Dark `danger` on `surface-1`: 5.90:1.
