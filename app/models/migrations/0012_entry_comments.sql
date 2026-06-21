-- 0012_entry_comments.sql
-- Entry comments (Task 1 of MEETING-2026-06-19-entry-comments): any logged-in
-- user who can already view an entry's detail can leave a free-text comment
-- on it. Comment permission piggybacks on the existing can_view_activity_detail
-- capability -- no new visibility tier, no separate gating column here.
--
-- Comments are co-owned, cross-user personal data: a comment is written by
-- author_id about another user's entry, so it must cascade-delete on deletion
-- of *either* account, not just the entry owner's. ON DELETE CASCADE from
-- entry(id) covers the entry-owner side (entry already cascades from user);
-- ON DELETE CASCADE from user(id) via author_id covers the commenter side.
--
-- Soft delete: comment rows are never hard-deleted by users, only by cascade
-- (per this project's archive-don't-delete convention) -- deleted_at marks a
-- user-initiated removal while still allowing audit/cascade integrity.

CREATE TABLE comment (
    id          INTEGER PRIMARY KEY,
    entry_id    INTEGER NOT NULL REFERENCES entry(id) ON DELETE CASCADE,
    author_id   INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    body        TEXT    NOT NULL CHECK (length(trim(body)) > 0),
    created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at  TEXT    NULL
);

-- Comment-thread list query (all comments for an entry, oldest first).
CREATE INDEX idx_comment_entry_created
    ON comment (entry_id, created_at);

-- Unseen-comment badge watermark, matching the user.consent_seen_at pattern
-- from 0005_user_visibility.sql.
ALTER TABLE user ADD COLUMN comments_seen_at TEXT NULL;
