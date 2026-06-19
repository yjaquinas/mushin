-- 0007_entry_time_known.sql
-- Add entry.time_known flag: 1 = exact timestamp supplied by the user,
-- 0 = timestamp is approximate (e.g. back-filled or date-only). Defaults
-- to 1 so all existing rows are treated as having a known time.

ALTER TABLE entry ADD COLUMN time_known INTEGER NOT NULL DEFAULT 1
