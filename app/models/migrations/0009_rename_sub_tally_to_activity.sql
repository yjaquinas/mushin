-- 0009_rename_sub_tally_to_activity.sql
-- Rename the sub_tally table and its FK columns across all child tables.
-- SQLite 3.26+ ALTER TABLE RENAME TO automatically updates FK constraint
-- text in child tables. SQLite 3.25+ RENAME COLUMN updates index column
-- references but NOT the index name — so we drop/recreate named indexes.

-- Step 1: Rename the table (FK references in child tables auto-update)
ALTER TABLE sub_tally RENAME TO activity;

-- Step 2: Rename FK columns in child tables
ALTER TABLE field_def   RENAME COLUMN sub_tally_id TO activity_id;
ALTER TABLE entry        RENAME COLUMN sub_tally_id TO activity_id;
ALTER TABLE level        RENAME COLUMN sub_tally_id TO activity_id;
ALTER TABLE level_rule   RENAME COLUMN sub_tally_id TO activity_id;

-- Step 3: Rename affected indexes (drop old name, create new name)
DROP INDEX idx_entry_subtally_time;
CREATE INDEX idx_entry_activity_time
    ON entry (activity_id, occurred_at DESC);

DROP INDEX idx_sub_tally_category_active;
CREATE INDEX idx_activity_category_active
    ON activity (category_id)
    WHERE archived_at IS NULL;

DROP INDEX idx_level_subtally_track_ordinal;
CREATE INDEX idx_level_activity_track_ordinal
    ON level (activity_id, track, ordinal);

-- Also rename the slug uniqueness index created by migration 0006
DROP INDEX IF EXISTS ux_sub_tally_owner_slug;
CREATE UNIQUE INDEX ux_activity_owner_slug
    ON activity (owner_id, slug)
    WHERE archived_at IS NULL;
