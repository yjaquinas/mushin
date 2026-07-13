# Mushin 無心 — Brand Guide

## Identity

**Mushin** (無心, "no-mind") is a social network for people who track. Users log entries against activities (workouts, reading, language study, gaming, recovery, etc.) on public profiles, connect as mutual "fellows," comment, and discover each other through search.

The brand mark is always **Mushin 無心** together. The kanji is never explained in UI beyond the one-line gloss — it's a brand signature, not a translation.

### Tagline

_Track. Share. Connect._

### One-line gloss

_No-mind. Just show up, and watch it add up._

## Voice

Warm, plain, second person. No hype, no urgency, no guilt framing. The tone is calm, patient, low-pressure — this is a long-view place, not a streaks-at-all-costs dashboard.

## Color Palette

### Light mode (default)

| Role                    | Hex       |
| ----------------------- | --------- |
| **Primary** (brand)     | `#0F172A` |
| Background              | `#F8FAFC` |
| Surface (cards, sheets) | `#FFFFFF` |
| **Accent** (cinnabar)   | `#E34234` |
| Text                    | `#0F172A` |

### Dark mode

| Role                    | Hex       |
| ----------------------- | --------- |
| **Primary** (brand)     | `#5A6B85` |
| Background              | `#0F172A` |
| Surface (cards, sheets) | `#1E293B` |
| **Accent** (cinnabar)   | `#FF6B5B` |
| Text                    | `#F8FAFC` |

### Non-swapping brand anchors

These hold their hex values regardless of theme (used in masthead, brand glyph):

| Name      | Hex       |
| --------- | --------- |
| Obsidian  | `#0F172A` |
| Cinnabar  | `#E34234` |
| Overlay   | `#121C30` |
| On-danger | `#EEE3CF` |

Accent is used sparingly — selected states, focus rings, progress bars, the tagline in OG imagery. It should never overwhelm. Primary is the dominant weight.

## App Icon

A simple, quiet mark representing emptiness / "no-mind" — not a literal translation, but a feeling. Directions: enso circle, minimalist vessel, a single centered dot, or one clean abstract stroke.

- Must read at 16×16 (favicon)
- No text, no people, no photography, no UI
- Must work on light (`#F8FAFC`) and dark (`#0F172A`) canvases

## OG Image (1200×630)

Preview card for link shares. Features **Mushin 無心** wordmark (primary) and **Track. Share. Connect.** tagline (accent). The icon mark sits as emblem. Open spacious background — light or dark. No photography, no people, no screenshots.

## Assets

Primary sources for look and feel:

- `app/static/src/input.css` — full design token definitions with rationale
- `app/ui_strings.py` — centralized UI copy (voice reference)

## Design Tokens

Design tokens are the source of truth. Token names must be semantic roles, not
raw colors, so all renderers share one palette.

### Role families in `@theme`

- `brand`, `brand-subtle`, `on-brand`
- `surface-0`, `surface-1`, `surface-2`
- `text-primary`, `text-secondary`, `text-muted`
- `border`, `border-strong`
- `accent`, `accent-subtle`, `accent-text`
- `level`, `level-subtle`
- `danger`, `danger-subtle`
- `heat-0` through `heat-4`

### Theme synchronization

Keep light/dark token values synchronized in:

1. `@theme { ... }`
2. `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { ... } }`
3. `[data-theme="dark"] { ... }`

Blocks 2 and 3 must stay identical. Light is the default theme unless a
recorded decision says otherwise. Accent and brand tokens should be used by
role, not by visual convenience. All surfaces should reuse the same token names
rather than maintaining a second palette.
