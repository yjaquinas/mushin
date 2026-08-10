-- Persist compact comment excerpts so notification history remains useful after
-- a comment or reply is soft-deleted.

ALTER TABLE notification ADD COLUMN comment_preview TEXT NULL;

-- The actor and timestamp identify the source comment for historical regular
-- comments and replies.  A reply notification's comment_id deliberately
-- remains the root-thread anchor, so it cannot be used for this lookup.
UPDATE notification
   SET comment_preview = (
       SELECT c.body
         FROM comment c
        WHERE c.entry_id = notification.entry_id
          AND c.author_id = notification.actor_id
          AND c.created_at = notification.created_at
        ORDER BY c.id
        LIMIT 1
   )
 WHERE type IN ('comment', 'comment_reply', 'comment_reply_participant')
   AND EXISTS (
       SELECT 1
         FROM comment c
        WHERE c.entry_id = notification.entry_id
          AND c.author_id = notification.actor_id
          AND c.created_at = notification.created_at
   );
