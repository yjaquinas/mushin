---
name: data-model
description: Mushin's canonical data model — the activity → entry model (category is an internal, invisible 1:1 wrapper, never a separate user-facing level), the field_def/entry_value recipe pattern, the always-running-count hero stat, the cache fields on activity, and the mandatory owner_id/index conventions. Use whenever writing or reviewing migrations, services that read/write entries, or stats.
---

# Mushin data model

The reference for how Mushin stores and queries data. Mushin is a personal
progress tracker: **activity → entry** (`category` is an internal,
automatically-created 1:1 wrapper behind every activity — never a separate
user-facing level, never a second creation step). SQLite, raw SQL, WAL,
`foreign_keys=ON`. Every owned row carries `owner_id`.

## The two levels

- **activity** — the thing a user tracks (e.g. "Workout", "Reading", "Kendo").
  Carries a recipe (its `field_def` set), and its own cached count/streak.
  `activity.slug TEXT` (unique per `owner_id` where `archived_at IS NULL`,
  migration 0006) is the canonical URL key for all **active** activities.
  `/@{username}/{slug}` is the single URL for an activity — the owner sees
  the editable dashboard view there; any other visitor sees the public
  read-only view (or the private stub, per `user.visibility`). `/activities/{id}`
  is retained only as the stable address for **archived** activities (whose
  slugs are not guaranteed unique once archived) and as the target for HTMX
  edit-mode fragment sub-routes (log, calendar, history, tags, match-rows)
  which are internal endpoints, not navigable URLs. When the owner renames an
  activity, the slug is **re-derived from the new name** via
  `unique_slug(conn, owner_id, new_name)` and updated atomically in the same
  transaction. The old slug becomes invalid (404) — there is no redirect
  table. Users are warned before confirming the rename. If URL stability is
  ever required, add an `activity_slug_history` table; don't add it
  speculatively.
- **entry** — belongs to an activity, has an editable `occurred_at` (defaults
  now, backfillable), and holds the values its recipe defines. An activity's
  entry stream can mix entry shapes freely — a free-form tag/count/memo log,
  a match-list result, and a level-up event can all be entries on the *same*
  activity, because the recipe lives on `field_def`, not on the entry.
- **category** — an internal row, 1:1 with an activity, created automatically
  in the same transaction as the activity it belongs to
  (`create_activity()` inserts both, sharing the same `name`). It is never
  exposed as a separate creation step, never listed on its own, and never a
  concept a user names independently of the activity. It exists at the
  schema level so existing FK shape (`activity.category_id`) doesn't need to
  change; nothing should ever branch on "does this category have more than
  one activity" as steady-state behavior. Carries `icon TEXT` (nullable,
  Lucide icon name from `categories.ICON_CHOICES`; `NULL` falls back to
  `circle-dot`).

## The recipe: field_def + entry_value (EAV)

- `field_def` rows on an activity declare the recipe. `kind ∈ {tag_group,
  scale, count, memo, match_list}`. Form-rendering and stats
  iterate field defs — **no per-activity code**. An activity can have any
  combination of kinds.
- `entry_value(entry_id, field_def_id)` (composite PK) holds scalar values:
  `num_value REAL` / `text_value TEXT`, with `CHECK(num_value IS NOT NULL OR
  text_value IS NOT NULL)`. Scalars only.
- `tag` rows are reusable chips within a `tag_group` field; `entry_tag(entry_id,
  tag_id)` (composite PK) records selections.
- **`match` is its own table** (opponent, score, result win/loss/draw) — a
  structured multi-column fact, never scattered into entry_value. Keep `owner_id`
  on it too. A `match_list` field_def can live on the same activity as a
  running tag/count log — they share one entry stream.

## Hero stat: always the running count

An activity's hero stat is always the running count of its entries (per
week/month/year/lifetime). There is no progression mode, no `level`-kind
field_def, and no gating mechanism — that system was removed entirely
(2026-06). `config_json` (on activity / field_def) holds **only
never-queried display metadata**. If you'll ever `WHERE`/`JOIN` on it, it's
a column or row.

## Activity creation

Every activity, seeded or user-created, is the same shape — `memo` and
`tag_group` field_defs by default. `app/services/categories.create_activity()`
is the one write path. No templates are seeded on signup; new accounts start
with zero activities.

## Cache discipline

`activity` carries `cached_count`, `cached_streak`, `last_entry_at`, written
**in the same transaction** as entry writes. A `recompute(activity_id,
owner_id)` rebuilds them from truth (drift guard). The home screen reads the
cache, never re-aggregates on every render.

## owner_id, archiving, deletion

- **`owner_id` on every owned table**, and **every query takes `owner_id` as a
  required argument** (use the accessor helper). Multi-user isolation is the
  project's non-negotiable invariant.
- **Archive, don't delete** categories/activities/tags: `archived_at TEXT`
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
  `/@{username}` (activity names + counts, cards not clickable);
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

## Comments on entries

- `comment(id, entry_id, author_id, body, created_at, deleted_at)` — both
  `entry_id` and `author_id` are `ON DELETE CASCADE` (a comment is co-owned by
  the commenter and the entry's owner; either account's deletion must remove
  it, no orphans).
- Comment visibility is **never stored**. Every read re-evaluates
  `can_view_activity_detail()` for the current viewer against the comment's
  parent entry. Revoking a fellow connection, blocking, or flipping a profile
  public→private does not delete old comments; it simply makes them stop
  rendering to whoever lost access.
- `user.comments_seen_at` is a watermark column (same shape as the existing
  `user.consent_seen_at`). It is written only when the owner visits
  `/comments` (the notification history page) — never on home-page load —
  and is read in two places: the home badge count (`unseen_comment_count`)
  and the per-row "new since last visit" flag on `/comments` itself
  (`created_at > comments_seen_at`, computed before the watermark is
  advanced). Still not a notification table — the history page is a `SELECT`
  over the existing `comment` table, joined to `entry`/`activity`/`user`;
  per-comment read-state is never stored.
- **Blocking does not retroactively filter the owner's own notification
  feed.** If the owner blocks a fellow after that fellow commented, the
  fellow's past comments stay visible in the owner's `/comments` history —
  it's the owner's own data and a historical record, and removing it would
  create a reverse existence-oracle (a gap in the feed would itself signal
  "you blocked someone"). Blocking still does its real job going forward: it
  strips the blocked user's `can_comment_on_entry` (no new comments) and
  removes the owner from what the blocked user can see. This is distinct
  from the "revoked access stops rendering" rule above, which protects a
  *viewer* losing access to someone else's content — the owner never loses
  access to their own entries.

## Indexes (hot paths)

- `entry(activity_id, occurred_at DESC)` — the entry list and stats range scan.
- Partial indexes excluding archived rows (`… WHERE archived_at IS NULL`).
- `match(entry_id)`; partial `user(last_active_at) WHERE auth_provider='guest'`.

## Tables (canonical list)

`user, category, activity, field_def, tag, entry, entry_tag, entry_value,
match, connection, block, comment`. `category` is internal, 1:1
with `activity`, never exposed as a separate creation step or list. (`user`
gains `visibility`, `consent_seen_at` — migration 0005; `activity` gains
`slug` — migration 0006; `sub_tally` renamed to `activity` — migration 0009;
`connection`/`block` + `user.private_redefinition_seen_at` — migration 0010;
`level`/`level_rule` dropped and `field_def.kind` tightened — migration 0013,
2026-06.)
