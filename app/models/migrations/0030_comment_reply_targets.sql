-- Keep first-level reply threads flat while recording the specific comment addressed.

ALTER TABLE comment ADD COLUMN reply_to_comment_id INTEGER
    REFERENCES comment(id) ON DELETE SET NULL;

UPDATE comment
   SET reply_to_comment_id = parent_comment_id
 WHERE parent_comment_id IS NOT NULL;

CREATE INDEX idx_comment_reply_target
    ON comment (reply_to_comment_id);
