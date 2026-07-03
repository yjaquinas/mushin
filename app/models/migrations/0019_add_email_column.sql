-- 0019_add_email_column.sql
-- Add email column back to user table (dropped in 0018, needed for recovery)

ALTER TABLE user ADD COLUMN email TEXT NULL;
CREATE UNIQUE INDEX ux_user_email ON user(email) WHERE email IS NOT NULL;
