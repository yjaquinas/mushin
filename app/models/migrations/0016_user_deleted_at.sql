-- Soft account deletion: remove account access while preserving user history.

ALTER TABLE user ADD COLUMN deleted_at TEXT NULL;
