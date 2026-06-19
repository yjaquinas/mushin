-- 0002_category_icon.sql
-- Add a nullable icon column to category for user-chosen category icons.
-- NULL means "use the default icon (circle-dot)" - application code handles
-- the fallback. No backfill needed here.

ALTER TABLE category ADD COLUMN icon TEXT NULL;
