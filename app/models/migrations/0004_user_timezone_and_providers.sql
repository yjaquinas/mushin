-- 0004_user_timezone_and_providers.sql
-- Drop 'kakao' from user.auth_provider (Mushin is repositioned English-only
-- and US-targeted, per meetings/MEETING-2026-06-15-drop-korean-targeting) and
-- add user.timezone (IANA name) to drive day/week-boundary calculations.
--
-- SQLite can't ALTER a CHECK constraint in place, so this is the standard
-- rebuild: create user_new with the updated CHECK + new column, copy rows,
-- drop the old table, rename. The CHECK on user_new doubles as the guard
-- against stale 'kakao' rows -- if any exist, the INSERT below violates the
-- CHECK and the whole migration transaction rolls back.

CREATE TABLE user_new (
    id               INTEGER PRIMARY KEY,
    auth_provider    TEXT    NOT NULL CHECK (auth_provider IN ('google', 'email', 'guest')),
    provider_id      TEXT    NULL,
    password_hash    TEXT    NULL,
    display_name     TEXT    NULL,
    username         TEXT    NULL,
    email            TEXT    NULL,
    timezone         TEXT    NOT NULL DEFAULT 'UTC',
    created_at       TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_active_at   TEXT    NULL
);

INSERT INTO user_new (id, auth_provider, provider_id, password_hash, display_name, username, email, timezone, created_at, last_active_at)
SELECT id, auth_provider, provider_id, password_hash, display_name, username, email, 'UTC', created_at, last_active_at
FROM user;

DROP TABLE user;

ALTER TABLE user_new RENAME TO user;

-- Recreate indexes that lived on the old user table.

CREATE UNIQUE INDEX ux_user_username ON user(username) WHERE username IS NOT NULL;
CREATE UNIQUE INDEX ux_user_email    ON user(email)    WHERE email    IS NOT NULL;

CREATE INDEX idx_user_guest_last_active
    ON user (last_active_at)
    WHERE auth_provider = 'guest';
