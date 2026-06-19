-- 0005_user_visibility.sql
-- Public/private profile feature (Phase 1): add user.visibility, defaulting
-- existing and new accounts to 'private', and user.consent_seen_at to track
-- whether the one-time visibility-explainer screen has been shown.
--
-- Both are simple ADD COLUMN statements -- SQLite supports a column-level
-- CHECK + DEFAULT on ADD COLUMN as long as the CHECK only references the new
-- column itself (no subqueries / other-row references), which is the case
-- here. No table rebuild needed (contrast with 0004, where the CHECK had to
-- be revalidated against existing rows of an existing column).

ALTER TABLE user ADD COLUMN visibility TEXT NOT NULL DEFAULT 'private'
    CHECK (visibility IN ('public', 'private'));

ALTER TABLE user ADD COLUMN consent_seen_at TEXT NULL;
