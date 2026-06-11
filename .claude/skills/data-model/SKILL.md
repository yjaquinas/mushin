---
name: data-model
description: Mushin's canonical data model — the category → sub-tally → entry hierarchy, the field_def/entry_value recipe pattern, count modes (running/progression), the four progression gate types, the derived-not-stored progression rule, levels-as-rows, the cache fields on sub_tally, and the mandatory owner_id/index conventions. Use whenever writing or reviewing migrations, services that read/write entries, stats, progression math, or template seeding.
---

# Mushin data model

The reference for how Mushin stores and queries data. Mushin is a personal
progress tracker: **category (activity) → sub-tally → entry**. SQLite, raw SQL,
WAL, `foreign_keys=ON`. Every owned row carries `owner_id`.

## The three levels

- **category** — an activity domain (검도, 독서, …).
- **sub_tally** — carries a recipe (its field set), a `count_mode`, and its own
  cached count/streak/progression. A category has one or more; single-sub-tally
  categories hide the layer in the UI.
- **entry** — belongs to a sub-tally, has an editable `occurred_at` (defaults
  now, backfillable), and holds the values its recipe defines.

## The recipe: field_def + entry_value (EAV)

- `field_def` rows on a sub_tally declare the recipe. `kind ∈ {tag_group, scale,
  count, memo, match_list, level, result}`. Form-rendering and stats iterate
  field defs — **no per-activity code**.
- `entry_value(entry_id, field_def_id)` (composite PK) holds scalar values:
  `num_value REAL` / `text_value TEXT`, with `CHECK(num_value IS NOT NULL OR
  text_value IS NOT NULL)`. Scalars only.
- `tag` rows are reusable chips within a `tag_group` field; `entry_tag(entry_id,
  tag_id)` (composite PK) records selections.
- **`match` is its own table** (opponent, score, result win/loss/draw) — a
  structured multi-column fact, never scattered into entry_value. Keep `owner_id`
  on it too.

## Count modes

- **running** — monotonic count, reported per week/month/year/lifetime. The
  default.
- **progression** — a count plus a level track (see below).

## Progression: levels-as-rows, status derived

- **Levels are first-class `level` rows** (`track`, `ordinal`, `code`, `label`),
  not JSON. `track` separates the primary ladder (e.g. kendo dan) from a parallel
  prestige track (shōgō 연사/교사/범사).
- **`level_rule`** gates transitions: `from_level_id`, `to_level_id`,
  `gate_type ∈ {time, count, event, manual}`, `gate_value`, `min_age`,
  `prereq_level_id` (cross-track prerequisite, real FK).
- **Status is derived, not stored.** Current stage, time/progress-in-stage, and
  eligibility come from the ordered levels + the user's level entries +
  level_rule. **Batch per category** to avoid N+1. **Never cache eligibility** —
  a time-gate flips with no new entry. You may cache the *stage you're in*.
- `config_json` (on sub_tally / field_def) holds **only never-queried display
  metadata**. If you'll ever `WHERE`/`JOIN` on it, it's a column or row.

## Cache discipline

`sub_tally` carries `cached_count`, `cached_streak`, `last_entry_at`, written
**in the same transaction** as entry writes. A `recompute(sub_tally_id,
owner_id)` rebuilds them from truth (drift guard). The home screen reads the
cache, never re-aggregates on every render.

## owner_id, archiving, deletion

- **`owner_id` on every owned table**, and **every query takes `owner_id` as a
  required argument** (use the accessor helper). Multi-user isolation is the
  project's non-negotiable invariant.
- **Archive, don't delete** categories/sub-tallies/tags: `archived_at TEXT`
  (nullable timestamp). List queries carry `WHERE archived_at IS NULL`.
- **`ON DELETE CASCADE` from `user`** so account/guest deletion erases everything
  (PIPA, incl. memos).

## Accounts incl. guests

`user.auth_provider ∈ {kakao, google, email, guest}`; `provider_id` NULL for
guests; `last_active_at` feeds the guest-reaper. Guest data lives in the same
server SQLite as everyone else (anonymous server account, not on-device).

## Indexes (hot paths)

- `entry(sub_tally_id, occurred_at DESC)` — the entry list and stats range scan.
- Partial indexes excluding archived rows (`… WHERE archived_at IS NULL`).
- `match(entry_id)`; `level(sub_tally_id, track, ordinal)`; partial
  `user(last_active_at) WHERE auth_provider='guest'`.

## Tables (canonical list)

`user, category, sub_tally, field_def, tag, entry, entry_tag, entry_value,
match, level, level_rule`.
