-- Preserve which entry owner hid a comment so the public placeholder can
-- identify the person who moderated it. Existing administrator-hidden rows
-- intentionally remain NULL and continue to render as moderator-hidden.

ALTER TABLE comment ADD COLUMN hidden_by_id INTEGER NULL REFERENCES user(id) ON DELETE SET NULL;
