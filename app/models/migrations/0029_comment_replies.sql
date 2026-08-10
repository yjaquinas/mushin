-- First-level comment replies and their notification targets.

ALTER TABLE comment ADD COLUMN parent_comment_id INTEGER
    REFERENCES comment(id) ON DELETE CASCADE;

CREATE INDEX idx_comment_entry_parent_created
    ON comment (entry_id, parent_comment_id, created_at, id);

CREATE TABLE notification_new (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    type       TEXT NOT NULL CHECK (type IN ('comment', 'comment_reply', 'comment_reply_participant', 'connection_request', 'connection_accepted')),
    actor_id   INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    entry_id   INTEGER REFERENCES entry(id) ON DELETE SET NULL,
    comment_id INTEGER REFERENCES comment(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    read_at    TEXT NULL
);

INSERT INTO notification_new (id, user_id, type, actor_id, entry_id, created_at, read_at)
SELECT id, user_id, type, actor_id, entry_id, created_at, read_at
  FROM notification;

DROP TABLE notification;

ALTER TABLE notification_new RENAME TO notification;

CREATE INDEX idx_notification_user_created
    ON notification (user_id, created_at DESC, id DESC);

CREATE INDEX idx_notification_user_unread
    ON notification (user_id, created_at DESC, id DESC)
    WHERE read_at IS NULL;

CREATE UNIQUE INDEX ux_notification_comment_reply_root
    ON notification (user_id, comment_id)
    WHERE type = 'comment_reply';
