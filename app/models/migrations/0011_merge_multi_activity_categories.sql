-- 0011_merge_multi_activity_categories.sql
-- Domain-model collapse (category stops being a second user-facing level,
-- see Task 3 of MEETING-2026-06-19-home-layout-fix): any account seeded
-- before that change still has the old shape -- one category with several
-- child activities (the pre-collapse Kendo template: "Practice",
-- "Tournament", "Grading"). This migration finds every such category and
-- merges its non-archived activities onto one survivor.
--
-- Survivor selection: MIN(id) among the category's non-archived activities --
-- same tie-break convention as migration 0008's tag de-duplication (winner =
-- lowest id, losers archived not deleted).
--
-- For each loser activity, re-point its field_def/entry/level/level_rule rows
-- onto the survivor, then archive the loser activity row (archived_at =
-- now) -- never DELETE, per this project's archive-don't-delete convention.
--
-- field_def.sort_order is renumbered on the way over so a loser's fields
-- land after the survivor's existing fields rather than colliding/
-- interleaving with them: each loser's field_defs are offset by the
-- survivor's current MAX(sort_order) + 1, preserving each loser's *internal*
-- relative order while appending them after the survivor's own fields.
--
-- entry_value/entry_tag/match are untouched -- they key off entry_id (which
-- does not change) and entry.field_def_id linkage continues to resolve
-- correctly once field_def.activity_id is repointed.
--
-- Idempotent: after the first run every formerly-multi-activity category has
-- exactly one non-archived activity, so the "categories with > 1 active
-- activity" set is empty on every subsequent run -- a true no-op, including
-- against a fresh database or one where this shape never existed (the
-- expected production case).
--
-- The migration runner (app/models/migrate.py) wraps every statement in this
-- file in a single transaction -- there is no per-category transaction
-- boundary available at the .sql-file level (matching every prior batch
-- migration in this codebase, e.g. 0006, 0008). The set-based UPDATEs below
-- operate on all qualifying categories across all owners in one pass.
-- Because each row's update is keyed entirely off its own category_id /
-- activity_id, this is equivalent in outcome to looping per-category, and is
-- just as safe to retry.

-- Step 0: a temp table pinning each multi-activity category's survivor id
-- (MIN(id) among its non-archived activities) and the survivor's current
-- max field_def sort_order, computed once so later steps don't recompute a
-- moving target mid-migration.
CREATE TEMP TABLE _activity_merge_survivor AS
SELECT
    a.category_id                              AS category_id,
    MIN(a.id)                                   AS survivor_id,
    COALESCE(
        (SELECT MAX(fd.sort_order)
           FROM field_def fd
          WHERE fd.activity_id = MIN(a.id)),
        -1
    )                                           AS survivor_max_sort_order
FROM activity a
WHERE a.archived_at IS NULL
GROUP BY a.category_id
HAVING COUNT(*) > 1;

-- Step 0b: a temp table of every loser activity (non-survivor, non-archived,
-- in a category that has a survivor row above) paired with its survivor id
-- and a per-loser ordinal (lowest loser id gets offset block 0, next loser
-- gets the next block, etc.) so multiple losers' field_defs don't collide
-- with each other either.
CREATE TEMP TABLE _activity_merge_loser AS
SELECT
    a.id                                        AS loser_id,
    s.survivor_id                               AS survivor_id,
    s.survivor_max_sort_order
        + 1
        + (
            SELECT COUNT(*) FROM activity a2
             WHERE a2.category_id = a.category_id
               AND a2.archived_at IS NULL
               AND a2.id < a.id
               AND a2.id <> s.survivor_id
          ) * 1000                              AS sort_order_offset
FROM activity a
JOIN _activity_merge_survivor s ON s.category_id = a.category_id
WHERE a.archived_at IS NULL
  AND a.id <> s.survivor_id;

-- Step 1: re-point field_def rows from losers to the survivor, renumbering
-- sort_order so each loser's fields append after the survivor's own fields
-- (and after any earlier loser's fields) while preserving each loser's
-- internal relative ordering.
UPDATE field_def
   SET activity_id = (
           SELECT survivor_id FROM _activity_merge_loser
            WHERE loser_id = field_def.activity_id
       ),
       sort_order = (
           SELECT sort_order_offset FROM _activity_merge_loser
            WHERE loser_id = field_def.activity_id
       ) + sort_order
 WHERE activity_id IN (SELECT loser_id FROM _activity_merge_loser);

-- Step 2: re-point entry rows from losers to the survivor.
UPDATE entry
   SET activity_id = (
           SELECT survivor_id FROM _activity_merge_loser
            WHERE loser_id = entry.activity_id
       )
 WHERE activity_id IN (SELECT loser_id FROM _activity_merge_loser);

-- Step 3: re-point level rows from losers to the survivor.
UPDATE level
   SET activity_id = (
           SELECT survivor_id FROM _activity_merge_loser
            WHERE loser_id = level.activity_id
       )
 WHERE activity_id IN (SELECT loser_id FROM _activity_merge_loser);

-- Step 4: re-point level_rule rows from losers to the survivor.
UPDATE level_rule
   SET activity_id = (
           SELECT survivor_id FROM _activity_merge_loser
            WHERE loser_id = level_rule.activity_id
       )
 WHERE activity_id IN (SELECT loser_id FROM _activity_merge_loser);

-- Step 5: archive (never delete) the absorbed loser activities.
UPDATE activity
   SET archived_at = datetime('now')
 WHERE id IN (SELECT loser_id FROM _activity_merge_loser)
   AND archived_at IS NULL;

DROP TABLE _activity_merge_loser;
DROP TABLE _activity_merge_survivor;
