-- Admin moderation controls.
-- Nullable timestamps make moderation reversible while preserving audit context.

ALTER TABLE user ADD COLUMN suspended_at TEXT NULL;

ALTER TABLE entry ADD COLUMN hidden_at TEXT NULL;

ALTER TABLE comment ADD COLUMN hidden_at TEXT NULL;

CREATE INDEX idx_entry_owner_visible
    ON entry (owner_id, activity_id, occurred_at DESC)
    WHERE hidden_at IS NULL;

CREATE INDEX idx_comment_entry_visible
    ON comment (entry_id, created_at)
    WHERE deleted_at IS NULL AND hidden_at IS NULL;
