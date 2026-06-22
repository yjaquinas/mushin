-- 0013_drop_progression.sql
-- Drop the progression/leveling system entirely, per
-- meetings/MEETING-2026-06-21-simplify-onboarding. Mushin's hero stat is
-- always the running count -- there is no level ladder, no gating mechanism.
--
-- Two changes:
-- 1. field_def.kind drops 'level' and 'result' from its CHECK (the standard
--    SQLite table-rebuild, since CHECK constraints can't be altered in
--    place). Any pre-existing rows with kind IN ('level', 'result') are
--    dropped during the copy rather than left to violate the new CHECK --
--    on a fresh/empty db there are none, but this keeps the migration safe
--    for any database that already has data.
-- 2. The level and level_rule tables are dropped outright (level_rule first
--    -- it holds FKs into level via from_level_id/to_level_id/prereq_level_id,
--    so it must go before its parent).
--
-- match.result (win/loss/draw outcome on the match table) is untouched --
-- that's an unrelated column name collision with the 'result' field-kind
-- being removed here.

-- Step 1: rebuild field_def with the tightened CHECK.

CREATE TABLE field_def_new (
    id           INTEGER PRIMARY KEY,
    activity_id  INTEGER NOT NULL REFERENCES activity(id) ON DELETE CASCADE,
    kind         TEXT    NOT NULL CHECK (kind IN ('tag_group', 'scale', 'count', 'memo', 'match_list')),
    label        TEXT    NOT NULL,
    config_json  TEXT    NULL,
    sort_order   INTEGER NOT NULL DEFAULT 0
);

INSERT INTO field_def_new (id, activity_id, kind, label, config_json, sort_order)
SELECT id, activity_id, kind, label, config_json, sort_order
FROM field_def
WHERE kind NOT IN ('level', 'result');

DROP TABLE field_def;

ALTER TABLE field_def_new RENAME TO field_def;

-- field_def itself has no indexes beyond its PK in 0001-0012, so there is
-- nothing to recreate here. (tag/entry_value carry the FK into field_def_id
-- and are untouched by this rebuild -- SQLite's automatic FK-name update on
-- ALTER TABLE RENAME TO keeps their REFERENCES field_def(id) clauses valid.)

-- Step 2: drop the progression tables. level_rule first (FKs into level).

DROP TABLE level_rule;
DROP TABLE level;

-- idx_level_activity_track_ordinal lived on `level` and is dropped
-- automatically with the table, but DROP INDEX IF EXISTS here is cheap
-- insurance against any environment where that didn't happen.
DROP INDEX IF EXISTS idx_level_activity_track_ordinal;
