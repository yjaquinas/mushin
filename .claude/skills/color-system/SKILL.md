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
