---
name: data-model
description: Mushin's canonical data model — the category → sub-tally → entry hierarchy, the field_def/entry_value recipe pattern, count modes (running/progression), the four progression gate types, the derived-not-stored progression rule, levels-as-rows, the cache fields on sub_tally, and the mandatory owner_id/index conventions. Use whenever writing or reviewing migrations, services that read/write entries, stats, progression math, or template seeding.
---

# Mushin data model

The reference for how Mushin stores and queries data. Mushin is a personal
progress tracker: **category (activity) → sub-tally → entry**. SQLite, raw SQL,
WAL, `foreign_keys=ON`. Every owned row carries `owner_id`.

## The three levels

- **category** — an activity domain, user-created (e.g. "Workout",
  "Reading"). Carries `icon TEXT` (nullable, Lucide icon name from
  `categories.ICON_CHOICES`; `NULL` falls back to `circle-dot`).
- **sub_tally** — carries a recipe (its field set), a `count_mode`, and its own
  cached count/streak/progression. A category has one or more; single-sub-tally
  categories hide the layer in the UI. `sub_tally.slug TEXT` (unique per
  `owner_id` where `archived_at IS NULL`, migration 0006) is the canonical URL
  key for all **active** sub-tallies. `/@{username}/{slug}` is now the single
  URL for an activity — the owner sees the editable dashboard view there; any
  other visitor sees the public read-only view (or the private stub, per
  `user.visibility`). `/activities/{id}` is retained only as the stable address
  for **archived** sub-tallies (whose slugs are not guaranteed unique once
  archived) and as the target for HTMX edit-mode fragment sub-routes (log,
  calendar, history, tags, match-rows) which are internal endpoints, not
  navigable URLs. When the owner renames an activity (`sub_tally.name`), the slug
  is **re-derived from the new name** via `unique_slug(conn, owner_id, new_name)`
  and updated atomically in the same transaction. The old slug becomes invalid
  (404) — there is no redirect table. Users are warned before confirming the
  rename. If URL stability is ever required, add a `sub_tally_slug_history` table;
  don't add it speculatively.
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

## General-log categories (default for user-created)

A user-created category is, by default, a single `sub_tally` with
`count_mode="running"` and exactly two `field_def` rows: `memo` and
`tag_group`. No progression, no `level`/`level_rule` rows. This is the
"general log" shape — `app/services/categories.create_category()` is the one
write path for it. The kendo/reading seed templates (richer recipes with
progression) remain in the codebase as a future opt-in template gallery, not
auto-seeded on signup.

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
  (incl. memos).

### Entry time precision

`entry.time_known INTEGER NOT NULL DEFAULT 1` (migration 0007) — set to `1`
when the entry's `occurred_at` includes a meaningful time component (user-entered
AM/PM time), `0` when the entry was logged date-only. Existing entries backfill as
`1` (they have real server timestamps). Display shows the time only when
`time_known=1`; otherwise shows date only (YYYY-MM-DD, no clock).

`occurred_at` continues to store full ISO datetime. For date-only entries, the
time component is stored as local midnight (`00:00:00`) with `time_known=0`.

## Accounts incl. guests

`user.auth_provider ∈ {google, email, guest}`. Guest creation is **retired**
as a user-facing entry point (2026-06-16) — new signups require username +
password or Google OAuth. Existing guest rows (`auth_provider='guest'`,
`provider_id NULL`) continue to drain via the guest-reaper timer on their normal
schedule; schema and service code stay intact during the drain window. Guest
dead-code removal (CHECK constraint, reaper service/timer, route branches) is a
separate future cleanup once the backlog clears.

`user.visibility ∈ {public, private}` (default `private`) controls whether
`/@{username}` and `/@{username}/{activity-slug}` render full content
(public) or a minimal "this page is private" stub that only confirms the
username exists (private). **(Superseded once migration 0010 lands — see
"Social graph + 3-tier visibility" below: `private` shows a character sheet,
not a stub, and the slug route 303-redirects non-connected viewers.)**
`user.consent_seen_at TEXT NULL` tracks whether
the user has been shown the one-time visibility-explainer screen — accounts
with `auth_provider='guest'` skip this entirely (no `username` ⇒ no public
URL, always effectively private).

## Social graph + 3-tier visibility (fellows)

A **fellow** is a mutual connection. Two tables, both with dual
`ON DELETE CASCADE` from `user` (deletion wipes the graph both directions):

- **`connection`** — the directed handshake: `(requester_id, addressee_id,
  status ∈ pending/accepted/declined)` plus a canonical directionless pair
  `(user_lo, user_hi)` with `UNIQUE(user_lo, user_hi)` so A→B and B→A can't both
  exist. `sharing_consent_at` is stamped when the request is accepted via the
  deliberate consequence-screen confirm; reaching `connected` capability
  requires `status='accepted' AND sharing_consent_at IS NOT NULL` (not merely
  "a row exists").
- **`block`** — `(blocker_id, blocked_id)` unique, dual cascade. A block is
  silent and **indistinguishable from non-existence** in search and direct
  navigation (no existence oracle).

**Visibility is three-tier, not binary.** `user.visibility ∈ {public, private}`
still, but `private` no longer means hidden:

- **public** — whole record (activities + entries + notes) visible to anyone.
- **private** — a non-connected visitor sees the **character sheet** at
  `/@{username}` (activity names + levels/progress/counts, cards not clickable);
  forcing `/@{username}/{slug}` **303-redirects** to the profile. Entries +
  notes stay gated.
- **fellow** (accepted + consented connection) — full record incl. entries and
  free-text notes, on either account.

All accounts are searchable by username/display name. **The single fail-closed
authority** is `app/services/profiles.py::viewer_capability(conn,
current_user_id, profile_user) -> owner | connected | limited | public`
(precedence owner > connected > public > limited) plus `can_view_activity_detail`.
Routes branch on the capability; **none read `user.visibility` directly**, and a
capability is **never cached** (a stale capability is a bypass). Search: people
search returns handle + display name + relationship state only (never
activity/entry/note data); **tag search is public-only** and structurally
incapable of returning private/limited accounts or matching note/entry text.
The re-consent flag `user.private_redefinition_seen_at` gates existing private
users into a one-time re-consent before their character sheet is exposed.

## Indexes (hot paths)

- `entry(sub_tally_id, occurred_at DESC)` — the entry list and stats range scan.
- Partial indexes excluding archived rows (`… WHERE archived_at IS NULL`).
- `match(entry_id)`; `level(sub_tally_id, track, ordinal)`; partial
  `user(last_active_at) WHERE auth_provider='guest'`.

## Tables (canonical list)

`user, category, sub_tally, field_def, tag, entry, entry_tag, entry_value,
match, level, level_rule, connection, block`. (`user` gains `visibility`,
`consent_seen_at` — migration 0005; `sub_tally` gains `slug` — migration 0006;
`connection`/`block` + `user.private_redefinition_seen_at` — migration 0010.)
