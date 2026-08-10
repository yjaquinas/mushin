-- Give pre-reply comment notifications an exact in-thread anchor where possible.

UPDATE notification
   SET comment_id = (
       SELECT c.id
         FROM comment c
        WHERE c.entry_id = notification.entry_id
          AND c.author_id = notification.actor_id
          AND c.created_at = notification.created_at
        ORDER BY c.id
        LIMIT 1
   )
 WHERE type = 'comment'
   AND comment_id IS NULL
   AND EXISTS (
       SELECT 1
         FROM comment c
        WHERE c.entry_id = notification.entry_id
          AND c.author_id = notification.actor_id
          AND c.created_at = notification.created_at
   );
