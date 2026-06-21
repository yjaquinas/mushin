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

## Brand realignment (2026-06-19)

Mushin is repainting to match the aqnas-studio brand identity (the CEO's own
studio, https://aqnas.xyz — Mushin is the studio's flagship product). The CEO
supplied this source palette directly:

| Name            | Hex       | Given role             |
|-----------------|-----------|-------------------------|
| obsidian        | `#0F172A` | dark background         |
| cinnabar        | `#E34234` | accent                  |
| alabaster       | `#F8FAFC` | light text / light bg   |
| alabaster-dim   | `#F1F5F9` | subtle background       |
| slate           | `#94A3B8` | muted text              |
| slate-mid       | `#64748B` | medium text             |
| surface-dark    | `#1E293B` | dark surface            |
| border          | `#E2E8F0` | light border             |
| border-dark     | `#334155` | dark border              |

**The existing semantic-role architecture stays the source of truth** —
`surface-0/1/2`, `text-primary/secondary/muted`, `border`/`border-strong`,
`accent`/`accent-subtle`, `level`/`level-subtle`, `danger`/`danger-subtle`,
`heat-0..4` are still what templates consume, and still swap value between
light and dark (and will map to HXML attributes at native parity). The brand
palette above maps *onto* these roles — it does not replace the role
contract. Rough mapping (ui-stylist finalizes exact values and dark-mode
pairs as part of the build task):

- `alabaster` / `alabaster-dim` → the light-mode `surface-*` family (exact
  ordering — which is canvas vs. card vs. inset — is ui-stylist's call,
  using the existing rule that `surface-1` (card) reads lightest and
  `surface-2` (inset) reads darkest).
- `obsidian` / `surface-dark` / `border-dark` → the dark-mode `surface-*` /
  `border` family.
- `slate-mid` → `text-secondary` / `text-muted`. **`slate` itself must not
  be used as text color** — `slate` on `alabaster-dim` is ~2:1 contrast,
  far under the 4.5:1 text minimum. Reserve `slate` for borders, icons, and
  disabled states only.
- `cinnabar` → `--color-accent`, replacing today's ink-blue. Cinnabar on
  `alabaster` is ~3.6:1 — **fails 4.5:1 for body text.** Use cinnabar only
  for: button fills (with large/bold or white label text), icons, borders,
  chip-selected state, and focus rings — never as plain link/body text on a
  light surface. This is a tightening of the existing "never a
  meaning-bearing background fill alone" rule, not a new one.

**Two fixed, non-theme-swapping utilities** are added on top of the role
system: `--color-obsidian` (→ `bg-obsidian`) and `--color-cinnabar` (→
`bg-cinnabar`, `text-cinnabar`). These hold their literal hex value
regardless of `data-theme` — the same pattern `--color-level` already uses
today as a near-invariant, fixed-meaning token. Use them for deliberate
brand moments (e.g. the masthead band) where the color must not flip with
theme, never as a substitute for the swapping `accent`/`surface` roles in
ordinary UI.

**Danger/accent hue collision.** `cinnabar #E34234` and the existing
`--color-danger #b03a2e` are ~30° apart on the wheel — too close; both would
read as "warning red" to most users. Since cinnabar now owns "brand red" as
the accent, `--color-danger` must be re-hued away from the red family (a
cooler or notably darker red, or shift to a non-red hue entirely) so the two
remain visually distinct without relying on a side-by-side comparison. The
existing "never color alone" rule for danger affordances (icon + label) is
unchanged — this is purely a hue-separation fix layered on top of it.

**Heatmap ramp decoupling.** The current `heat-4 == accent` invariant is
**retired**, because `accent` is now cinnabar — a saturated red unsuited to
a calm intensity ramp. The heatmap keeps its own independent hue family
(the existing blue-toned ramp, or a recomputed calm hue), no longer tied to
whatever color `accent` happens to be. All other heat-ramp invariants
(`heat-0 == surface-2`, monotonic lightness/saturation, colorblind-safe
progression) still hold.

**Theme default is unchanged: light stays default.** Mushin is a
daily-logging tool (minutes of reading per session), not a 30-second
marketing hero — dark is kept as today's polished opt-in, not flipped to
default. Obsidian is used as a deliberate dark *band* (e.g. masthead) on an
otherwise light page, not a wholesale dark-first switch.

Both tables below were rewritten as part of Build Plan Task 1 with the
final computed hex values and WCAG contrast ratios. `--color-accent-text`
(a darkened, same-hue cinnabar variant) was added alongside `accent` /
`accent-subtle` — cinnabar's max possible contrast against any light
surface is ~4.1:1, so it cannot itself serve as text on a light surface
(see `TOKENS.md` for the naming rationale). `--color-danger` was re-hued
from `#b03a2e` (hue ~5.5°, nearly identical to cinnabar's hue ~4.8°) to
`#A6471C` (hue ~20°, rust/burnt-orange) for clear hue separation. The
heatmap ramp is now anchored on its own calm slate-blue family, terminating
at `#3D6FA3` (light) / `#5C92D6` (dark) — independent of `accent`.

## To define here when built

- The named palette (brand, surface, text, accent, success/level-up, muted).
- Token → Tailwind utility mapping and token → HXML attribute mapping.
- Usage rules (what each token is for; what not to use it for).

## Heatmap intensity ramp

Defined in `app/static/src/input.css`. Five steps, `--color-heat-0` through
`--color-heat-4`, monotonically increasing in lightness/saturation from
`surface-2` toward a calm slate-blue endpoint — colorblind-tolerant
(lightness alone signals intensity, not hue). `heat-0` equals `surface-2`
exactly, so an empty cell reads as "inset/empty," never as a card
background.

**`heat-4 == accent` is retired (2026-06-19).** `accent` is now cinnabar, a
saturated brand red unsuited to a calm intensity ramp — the heat ramp is
decoupled and keeps its own independent calm hue family, never terminating
on cinnabar.

| Token            | Light     | Dark      | Meaning                    |
|------------------|-----------|-----------|-----------------------------|
| `--color-heat-0` | `#F1F5F9` | `#2A3950` | zero entries (= surface-2) |
| `--color-heat-1` | `#DCE7F2` | `#324568` | low activity                |
| `--color-heat-2` | `#B6CCE3` | `#3D5A87` | moderate activity            |
| `--color-heat-3` | `#7FA3C9` | `#4A75AC` | high activity                |
| `--color-heat-4` | `#3D6FA3` | `#5C92D6` | busiest day(s) — own hue, independent of accent |

Bucket the entry count into 5 bins server-side and apply `.heat-cell--0`
through `.heat-cell--4`.

Step-to-step contrast ratios (adjacent steps, confirming monotonic
lightness):

- Light: heat-1/heat-0 1.14:1, heat-2/heat-1 1.32:1, heat-3/heat-2 1.59:1,
  heat-4/heat-3 2.00:1.
- Dark: heat-1/heat-0 1.22:1, heat-2/heat-1 1.38:1, heat-3/heat-2 1.47:1,
  heat-4/heat-3 1.48:1.

## Dark mode tokens

Defined in `app/static/src/input.css` under `[data-theme="dark"]` (explicit
choice) and mirrored under `@media (prefers-color-scheme: dark)` (system
default, no cookie set). Same token *names* as light — only values change, so
both renderers keep one token contract.

Tokens requiring a dark variant: `surface-0/1/2`, `text-primary/secondary/
muted`, `border` / `border-strong`, `accent` / `accent-subtle` /
`accent-text`, `level` / `level-subtle`, `danger` / `danger-subtle`, and the
full `heat-0..4` ramp.

Invariants that must hold in dark too:
- `heat-0 == surface-2` (empty cell reads as inset, not background).
- `heat-4` keeps its own independent calm hue — **`heat-4 == accent` is
  retired (2026-06-19)**, now that `accent` is cinnabar.
- The heat ramp is re-derived against the dark surfaces, not a naive
  darken of the light ramp.
- `accent-subtle` / `level-subtle` are light tints under dark text in light
  mode; in dark mode they need their own (dark) tint under light text —
  don't just invert. Re-check the chip-selected and level-up contrast pairs.
- The focus ring (`outline: 2px solid var(--color-accent)`) must clear WCAG
  non-text contrast (3:1) against both dark and light canvases.

### Token values: light vs dark (post 2026-06-19 brand realignment)

Repainted to the aqnas-studio palette: obsidian / cinnabar / alabaster /
slate. See "Brand realignment" above for the source palette and mapping
rationale.

| Token                    | Light     | Dark      | Notes |
|--------------------------|-----------|-----------|-------|
| `--color-surface-0`      | `#F8FAFC` | `#0F172A` | canvas (alabaster / obsidian) |
| `--color-surface-1`      | `#FFFFFF` | `#1E293B` | card / sheet (pure white / surface-dark) |
| `--color-surface-2`      | `#F1F5F9` | `#2A3950` | inset / pressed; = heat-0 (alabaster-dim / derived) |
| `--color-border`         | `#E2E8F0` | `#334155` | brand `border` / `border-dark` |
| `--color-border-strong`  | `#7C8AA0` | `#64748B` | darkened slate / slate-mid |
| `--color-text-primary`   | `#0F172A` | `#F8FAFC` | obsidian / alabaster |
| `--color-text-secondary` | `#475569` | `#94A3B8` | light: darker slate. dark: slate (slate-mid too dark on dark bg) |
| `--color-text-muted`     | `#64748B` | `#7E8CA3` | slate-mid (light) / lightened slate-mid (dark) |
| `--color-accent`         | `#E34234` | `#FF6B5B` | cinnabar / lightened cinnabar; non-text/fill/border/focus-ring use only |
| `--color-accent-subtle`  | `#FBE7E4` | `#3A2422` | light: pale tint under dark/accent-text. dark: dark desaturated tint under light text (chip-selected bg) |
| `--color-accent-text`    | `#982015` | `#FF6B5B` | darkened cinnabar (light) for body-size accent text; dark `accent` already clears 4.5:1 |
| `--color-level`          | `#2a7a4b` | `#5fae80` | unchanged — not part of the brand remap |
| `--color-level-subtle`   | `#e6f4ec` | `#1f3a2a` | unchanged |
| `--color-danger`         | `#A6471C` | `#E8855E` | re-hued off cinnabar (hue ~20° vs cinnabar's ~5°); rust/burnt-orange |
| `--color-danger-subtle`  | `#FBEAE3` | `#3D2A20` | dark tint counterpart |
| `--color-heat-0`         | `#F1F5F9` | `#2A3950` | = surface-2 |
| `--color-heat-1`         | `#DCE7F2` | `#324568` | |
| `--color-heat-2`         | `#B6CCE3` | `#3D5A87` | |
| `--color-heat-3`         | `#7FA3C9` | `#4A75AC` | |
| `--color-heat-4`         | `#3D6FA3` | `#5C92D6` | own calm hue — `heat-4 == accent` invariant retired |

Two fixed, non-theme-swapping tokens added on top of the role table:
`--color-obsidian` (`#0F172A`, always) and `--color-cinnabar` (`#E34234`,
always) — never overridden in either dark-mode block.

Contrast checks (WCAG, computed against the values above):

- **Light:** `text-primary` on `surface-0`: 17.06:1; on `surface-1`:
  17.85:1. `text-secondary` on `surface-1`: 7.58:1; on `surface-0`: 7.24:1.
  `text-muted` on `surface-1`: 4.76:1; on `surface-0`: 4.55:1; on
  `surface-2`: 4.34:1.
- **Light `accent` (non-text, 3:1 minimum):** on `surface-1`: 4.12:1; on
  `surface-0`: 3.94:1 — cinnabar's max possible contrast against any light
  surface is 4.12:1 (vs pure white), which is why it never carries
  body-size text on light. `accent-text` (the darkened variant) on
  `surface-1`: 8.23:1; on `accent-subtle`: 6.92:1 — clears 4.5:1
  independently.
- **Light `danger`:** on `surface-1`: 5.93:1; on `surface-0`: 5.67:1; on
  `surface-2`: 5.42:1.
- **Light `level`** (unchanged): on `surface-1`: 5.27:1; on `level-subtle`:
  4.65:1.
- **Light `border-strong`** (non-text, 3:1 minimum) on `surface-1`: 3.50:1.
- **Dark `text-primary`** on `surface-0`: 17.06:1; on `surface-1`: 13.98:1.
  `text-secondary` on `surface-1`: 5.71:1; on `surface-0`: 6.96:1.
  `text-muted` on `surface-1`: 4.30:1; on `surface-0`: 5.24:1.
- **Dark `accent`** on `surface-0`: 6.38:1; on `surface-1`: 5.23:1 — both
  clear the 3:1 non-text minimum for the global focus ring, and also clear
  4.5:1 as body text (used directly as `accent-text` in dark mode).
  `accent-text` on `accent-subtle`: 5.16:1.
- **Dark `danger`** on `surface-1`: 5.54:1; on `surface-0`: 6.76:1.
- **Dark `level`** (unchanged): on `surface-1`: 5.47:1; on `surface-0`:
  6.68:1; on `level-subtle`: 4.63:1.
- **Dark `border-strong`** (non-text) on `surface-1`: 3.07:1.

Heat ramp is re-derived from each mode's own `surface-2` toward its own
calm slate-blue endpoint (not a naive darken of the light ramp or a
recolor toward `accent`) — see the "Heatmap intensity ramp" section above
for the step-to-step contrast progression.
