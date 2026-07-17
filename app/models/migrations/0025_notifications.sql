CREATE TABLE IF NOT EXISTS notification (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    type       TEXT NOT NULL CHECK (type IN ('comment', 'connection_request', 'connection_accepted')),
    actor_id   INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    entry_id   INTEGER REFERENCES entry(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    read_at    TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_notification_user_created
    ON notification (user_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_notification_user_unread
    ON notification (user_id, created_at DESC, id DESC)
    WHERE read_at IS NULL;

INSERT INTO notification (user_id, type, actor_id, entry_id, created_at, read_at)
SELECT e.owner_id,
       'comment',
       c.author_id,
       c.entry_id,
       c.created_at,
       CASE
           WHEN u.comments_seen_at IS NOT NULL
            AND julianday(c.created_at) <= julianday(u.comments_seen_at)
           THEN u.comments_seen_at
           ELSE NULL
       END
  FROM comment c
  JOIN entry e ON e.id = c.entry_id
  JOIN user u ON u.id = e.owner_id
 WHERE c.author_id != e.owner_id
   AND c.deleted_at IS NULL;

INSERT INTO notification (user_id, type, actor_id, entry_id, created_at, read_at)
SELECT addressee_id,
       'connection_request',
       requester_id,
       NULL,
       created_at,
       NULL
  FROM connection
 WHERE status = 'pending';

INSERT INTO notification (user_id, type, actor_id, entry_id, created_at, read_at)
SELECT requester_id,
       'connection_accepted',
       addressee_id,
       NULL,
       responded_at,
       responded_at
  FROM connection
 WHERE status = 'accepted'
   AND responded_at IS NOT NULL;
