-- 0017_remove_category.sql
-- Remove the category table entirely. Activities become top-level:
--   user → activity → entry
--
-- The icon column moves from category → activity. Color is dropped
-- (never used on activity in the UI).
--
-- SQLite requires table recreation to drop columns, so we:
--   1. Add icon column to activity
--   2. Copy icon from category → activity
--   3. Recreate activity without category_id
--   4. Drop category

-- Step 1: Add icon column to activity (temporary, will be copied then kept).
ALTER TABLE activity ADD COLUMN icon TEXT NULL;

-- Step 2: Copy icon from category to activity.
UPDATE activity
   SET icon = (
           SELECT c.icon FROM category c
            WHERE c.id = activity.category_id
       )
 WHERE category_id IN (SELECT id FROM category);

-- Step 3: Recreate activity without category_id.
CREATE TABLE activity_new (
    id             INTEGER PRIMARY KEY,
    owner_id       INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    name           TEXT    NOT NULL,
    count_mode     TEXT    NOT NULL CHECK (count_mode IN ('running', 'progression')),
    config_json    TEXT    NULL,
    cached_count   INTEGER NOT NULL DEFAULT 0,
    cached_streak  INTEGER NOT NULL DEFAULT 0,
    last_entry_at  TEXT    NULL,
    sort_order     INTEGER NOT NULL DEFAULT 0,
    archived_at    TEXT    NULL,
    created_at     TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    slug           TEXT,
    icon           TEXT
);

INSERT INTO activity_new
    (id, owner_id, name, count_mode, config_json, cached_count, cached_streak,
     last_entry_at, sort_order, archived_at, created_at, slug, icon)
SELECT id, owner_id, name, count_mode, config_json, cached_count, cached_streak,
       last_entry_at, sort_order, archived_at, created_at, slug, icon
FROM activity;

DROP TABLE activity;
ALTER TABLE activity_new RENAME TO activity;

-- Step 4: Recreate indexes on activity (category_id index no longer needed).
CREATE UNIQUE INDEX ux_activity_owner_slug
    ON activity (owner_id, slug)
    WHERE archived_at IS NULL;

-- Step 5: Drop category table.
DROP TABLE category;
