# Design token naming contract

Single source of truth: `app/static/src/input.css`. This file documents the
naming convention so any renderer — Tailwind v4 today, HXML at native parity
(Phase 5) — consumes the same token names without a second palette ever
existing.

## §Palette

Tokens are named by **semantic role**, not by raw color name. `--color-accent`
tells you what the color is *for*; it never tells you a literal hue, because
the literal hue is allowed to change (and did, in the 2026-06-19 brand
realignment to obsidian/cinnabar/alabaster/slate — the role names didn't
change, only their values).

Role families, defined once in `@theme`:

- `brand` / `brand-subtle` / `on-brand` — the studio ink and the text/icon
  color that sits on top of it. Unlike `obsidian`/`cinnabar` below, these
  swap with theme like any other role token.
- `surface-0/1/2` — background layers (canvas / card / inset).
- `text-primary/secondary/muted` — text emphasis tiers.
- `border` / `border-strong` — dividers and outlines.
- `accent` / `accent-subtle` / `accent-text` — the one brand color, its pale
  tint, and a darkened variant safe for body-size text (see below).
- `level` / `level-subtle` — the single progression/success color.
- `danger` / `danger-subtle` — destructive-action color, deliberately a
  different hue family from `accent`.
- `heat-0..4` — the heatmap intensity ramp, independent hue family from
  `accent`.

## Light/dark swap convention

Every role token above swaps value between light and dark — same name, two
values, defined in three places that must stay in sync:

1. `@theme { ... }` — the light (default) values.
2. `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { ... } }`
   — system-dark default, only when the user hasn't explicitly chosen light.
3. `[data-theme="dark"] { ... }` — explicit user choice (cookie/toggle).

Blocks 2 and 3 must carry identical values for every token — they're the same
dark palette, reached by two different activation paths. When you change a
role token's dark value, change it in both blocks.

Light is the default theme (a daily-logging tool, not a marketing hero) —
never flip this default without an explicit decision recorded in a meeting.

## The two fixed-value exceptions

`--color-obsidian` and `--color-cinnabar` are declared **once**, only in
`@theme`, and never overridden in either dark-mode block. They hold their
literal hex value regardless of `data-theme` — for deliberate brand moments
(a masthead band, a fixed brand glyph) where the color must stay constant
rather than swap. Never use these as a substitute for the swapping
`surface-*`/`accent` roles in ordinary UI; they're the exception, not the
pattern. (`--color-on-brand` looks similar but is *not* one of these
exceptions — it swaps between light and dark like any other role token; see
`input.css`.)

## Why `accent-text` exists

`--color-accent` (cinnabar) cannot reach 4.5:1 text contrast against any
light surface — its max possible contrast against pure white is ~4.1:1.
`--color-accent-text` is a darkened, same-hue variant that independently
clears 4.5:1, for the rare case where accent-colored text is genuinely
needed on a light surface (e.g. the `.chip--selected` label). `accent`
itself is reserved for fills, borders, icons, and focus rings — 3:1
non-text contexts — never body-size text on a light surface.

## §Type scale

See `app/static/src/input.css`'s `--font-size-*` tokens and the
`typography` skill for the home-card hierarchy rule (one hero numeral per
card, everything else demoted to caption size).

## Where this is consumed today / tomorrow

- **Web (today):** Tailwind v4 auto-generates utilities from any
  `--color-*` / `--font-size-*` / etc. custom property named in `@theme`
  — `--color-cinnabar` → `bg-cinnabar` / `text-cinnabar`, no extra config.
- **Native (Phase 5, not yet built):** the same token names will map to
  HXML style attributes. When that lands, it reads this same file — never
  a second, hand-maintained palette.
