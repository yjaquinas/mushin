-- 0008_tag_active_unique.sql
-- Prevent duplicate active tags under the same (owner_id, field_def_id, name).
-- The tag input is switching from chips (chosen from a known set) to free-text
-- hashtag typing, so name deduplication must be enforced at the DB level.
--
-- Step 1: normalize existing active tag names to lowercase + trimmed.
-- Step 2: re-point entry_tag rows from duplicate tag IDs to the winner (MIN id),
--         then archive the losers.
-- Step 3: add a partial unique index on (owner_id, field_def_id, lower(name))
--         covering only active (non-archived) tags.
--
-- The runner wraps all statements in a single transaction, so this is atomic.

-- Step 1: normalize active tag names to lower(trim(name)).
UPDATE tag SET name = lower(trim(name)) WHERE archived_at IS NULL;

-- Step 2a: re-point entry_tag rows that reference a loser tag ID to the winner.
UPDATE entry_tag
   SET tag_id = (
       SELECT MIN(t2.id)
         FROM tag t2
        WHERE t2.owner_id    = (SELECT owner_id    FROM tag WHERE id = entry_tag.tag_id)
          AND t2.field_def_id = (SELECT field_def_id FROM tag WHERE id = entry_tag.tag_id)
          AND lower(t2.name)  = (SELECT lower(name)  FROM tag WHERE id = entry_tag.tag_id)
          AND t2.archived_at IS NULL
   )
 WHERE tag_id IN (
     -- loser IDs: active tags that are NOT the MIN(id) in their (owner_id, field_def_id, name) group
     SELECT id FROM tag
      WHERE archived_at IS NULL
        AND id NOT IN (
            SELECT MIN(id) FROM tag
             WHERE archived_at IS NULL
             GROUP BY owner_id, field_def_id, lower(name)
        )
 );

-- Step 2b: archive the loser tags (those not chosen as the canonical MIN(id) row).
UPDATE tag
   SET archived_at = datetime('now')
 WHERE archived_at IS NULL
   AND id NOT IN (
       SELECT MIN(id) FROM tag
        WHERE archived_at IS NULL
        GROUP BY owner_id, field_def_id, lower(name)
   );

-- Step 3: partial unique index — enforces uniqueness only among active tags.
CREATE UNIQUE INDEX IF NOT EXISTS idx_tag_active_name
    ON tag (owner_id, field_def_id, lower(name))
 WHERE archived_at IS NULL
