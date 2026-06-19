-- 0003_username_identity.sql
-- Add username + recovery email to user for the auth-entry-flow redesign
-- (username + password becomes the primary path, email is optional, for
-- future account recovery). Both nullable so guest/OAuth rows are unaffected.
-- Partial unique indexes so multiple NULL username/email rows don't collide.
--
-- Backfill: existing 'email' provider users (created via create_email_user)
-- store their email in display_name. Copy it into the new email column,
-- skipping any value that would collide with an existing/duplicate email so
-- the unique index below can be created safely.

ALTER TABLE user ADD COLUMN username TEXT NULL;
ALTER TABLE user ADD COLUMN email    TEXT NULL;

UPDATE user
SET email = display_name
WHERE auth_provider = 'email'
  AND email IS NULL
  AND display_name IS NOT NULL
  AND (
      SELECT COUNT(*) FROM user AS u2
      WHERE u2.auth_provider = 'email' AND u2.display_name = user.display_name
  ) = 1;

CREATE UNIQUE INDEX ux_user_username ON user(username) WHERE username IS NOT NULL;
CREATE UNIQUE INDEX ux_user_email    ON user(email)    WHERE email    IS NOT NULL;
