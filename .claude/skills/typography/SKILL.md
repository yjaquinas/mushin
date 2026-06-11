---
name: typography
description: Mushin's type scale, expressing the home-card hero-stat hierarchy (large hero numeral, secondary labels, caption-demoted metrics) in renderer-agnostic terms. Use when sizing any text or defining a type token. Stub — to be filled by ui-stylist as the UI lands.
---

# Mushin typography

> **Status: stub.** Filled by `ui-stylist` as the UI is built (Build Plan
> Phase 1–2). Until then, follow the principles below.

## Principles (binding even while stubbed)

- **Renderer-agnostic tokens**, like the color system — one type scale that maps
  to both Tailwind utilities and HXML style attributes.
- **The home-card hierarchy is the load-bearing rule:** one large **hero
  numeral** per activity card (current count or level), the activity name
  secondary, every other metric demoted to caption size. One hero per card — no
  competing numerals.
- Korean-first: pick a type scale that reads well for Korean at mobile sizes and
  stays legible at 1.5× system font scaling.

## To define here when built

- The type scale (hero numeral, title, body, caption) as named tokens.
- Token → Tailwind and token → HXML mappings.
- Weight usage (selected chips differ by weight, not color alone).
