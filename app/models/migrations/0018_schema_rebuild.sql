-- 0018_schema_rebuild.sql
-- Complete schema rebuild:
--   user: remove display_name, timezone, auth_provider, provider_id  visibility default → public
--   activity: remove count_mode, config_json  rename cached_count → count, cached_streak → streak
--   entry: add num_value, tags (consolidate field_def/entry_value/tag/entry_tag into entry)
--   drop: match, field_def, tag, entry_tag, entry_value
--   (category, level, level_rule already gone from prior migrations)

-- ── Drop derived tables ──

DROP TABLE IF EXISTS entry_value;
DROP TABLE IF EXISTS entry_tag;
DROP TABLE IF EXISTS tag;
DROP TABLE IF EXISTS field_def;
DROP TABLE IF EXISTS match;
DROP TABLE IF EXISTS comment;
DROP TABLE IF EXISTS connection;
DROP TABLE IF EXISTS block;
DROP TABLE IF EXISTS visitor_event;

-- ── Drop all indexes (SQLite indexes are database-scoped) ──
DROP INDEX IF EXISTS idx_block_blocked;
DROP INDEX IF EXISTS idx_comment_entry_created;
DROP INDEX IF EXISTS idx_comment_entry_visible;
DROP INDEX IF EXISTS idx_connection_addressee_status;
DROP INDEX IF EXISTS idx_connection_hi_status;
DROP INDEX IF EXISTS idx_connection_lo_status;
DROP INDEX IF EXISTS idx_entry_activity_time;
DROP INDEX IF EXISTS idx_entry_owner_visible;
DROP INDEX IF EXISTS idx_match_entry;
DROP INDEX IF EXISTS idx_tag_active_name;
DROP INDEX IF EXISTS idx_user_guest_last_active;
DROP INDEX IF EXISTS idx_visitor_event_country_seen;
DROP INDEX IF EXISTS idx_visitor_event_first_seen;
DROP INDEX IF EXISTS ux_activity_owner_slug;
DROP INDEX IF EXISTS ux_block_pair;
DROP INDEX IF EXISTS ux_connection_pair;
DROP INDEX IF EXISTS ux_user_email;
DROP INDEX IF EXISTS ux_user_username;

-- ── Rebuild user (remove display_name, timezone, auth_provider, provider_id) ──

CREATE TABLE user_new (
    id                         INTEGER PRIMARY KEY,
    username                   TEXT    NOT NULL,
    password_hash              TEXT    NOT NULL,
    visibility                 TEXT    NOT NULL DEFAULT 'public' CHECK (visibility IN ('public', 'private')),
    consent_seen_at            TEXT    NULL,
    private_redefinition_seen_at TEXT NULL,
    comments_seen_at           TEXT    NULL,
    suspended_at               TEXT    NULL,
    deleted_at                 TEXT    NULL,
    created_at                 TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_active_at             TEXT    NULL
);

CREATE UNIQUE INDEX ux_user_username ON user_new(username);

-- ── Rebuild activity (remove count_mode, config_json  rename cached_count → count, cached_streak → streak) ──

CREATE TABLE activity_new (
    id             INTEGER PRIMARY KEY,
    owner_id       INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    name           TEXT    NOT NULL,
    count          INTEGER NOT NULL DEFAULT 0,
    streak         INTEGER NOT NULL DEFAULT 0,
    last_entry_at  TEXT    NULL,
    sort_order     INTEGER NOT NULL DEFAULT 0,
    archived_at    TEXT    NULL,
    created_at     TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    slug           TEXT,
    icon           TEXT
);

CREATE UNIQUE INDEX ux_activity_owner_slug
    ON activity_new (owner_id, slug)
    WHERE archived_at IS NULL;

-- ── Rebuild entry (add num_value, tags from field system  keep existing columns) ──

CREATE TABLE entry_new (
    id           INTEGER PRIMARY KEY,
    owner_id     INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    activity_id  INTEGER NOT NULL REFERENCES activity(id) ON DELETE CASCADE,
    occurred_at  TEXT    NOT NULL,
    memo         TEXT    NULL,
    num_value    REAL    NULL,
    tags         TEXT    NULL,
    time_known   INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    hidden_at    TEXT    NULL
);

CREATE INDEX idx_entry_activity_time
    ON entry_new (activity_id, occurred_at DESC);

CREATE INDEX idx_entry_owner_visible
    ON entry_new (owner_id, activity_id, occurred_at DESC)
    WHERE hidden_at IS NULL;

-- ── Recreate comment ──

CREATE TABLE comment (
    id          INTEGER PRIMARY KEY,
    entry_id    INTEGER NOT NULL REFERENCES entry(id) ON DELETE CASCADE,
    author_id   INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    body        TEXT    NOT NULL CHECK (length(trim(body)) > 0),
    created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at  TEXT    NULL,
    hidden_at   TEXT    NULL
);

CREATE INDEX idx_comment_entry_created
    ON comment (entry_id, created_at);

CREATE INDEX idx_comment_entry_visible
    ON comment (entry_id, created_at)
    WHERE deleted_at IS NULL AND hidden_at IS NULL;

-- ── Recreate connection ──

CREATE TABLE connection (
    id                      INTEGER PRIMARY KEY,
    requester_id            INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    addressee_id            INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    status                  TEXT    NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'declined')),
    user_lo                 INTEGER NOT NULL,
    user_hi                 INTEGER NOT NULL,
    sharing_consent_at      TEXT    NULL,
    created_at              TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    responded_at            TEXT    NULL,
    CHECK (requester_id <> addressee_id),
    CHECK (user_lo < user_hi)
);

CREATE UNIQUE INDEX ux_connection_pair
    ON connection (user_lo, user_hi);

CREATE INDEX idx_connection_addressee_status
    ON connection (addressee_id, status);

CREATE INDEX idx_connection_lo_status
    ON connection (user_lo, status);

CREATE INDEX idx_connection_hi_status
    ON connection (user_hi, status);

-- ── Recreate block ──

CREATE TABLE block (
    id          INTEGER PRIMARY KEY,
    blocker_id  INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    blocked_id  INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (blocker_id <> blocked_id)
);

CREATE UNIQUE INDEX ux_block_pair
    ON block (blocker_id, blocked_id);

CREATE INDEX idx_block_blocked
    ON block (blocked_id);

-- ── Recreate visitor_event ──

CREATE TABLE visitor_event (
    id             INTEGER PRIMARY KEY,
    visitor_key    TEXT NOT NULL,
    bucket_start   TEXT NOT NULL,
    first_seen_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    seen_count     INTEGER NOT NULL DEFAULT 1,
    ip_address     TEXT NULL,
    country_code   TEXT NULL,
    country_name   TEXT NULL,
    region         TEXT NULL,
    city           TEXT NULL,
    referrer       TEXT NULL,
    referrer_host  TEXT NULL,
    landing_path   TEXT NOT NULL,
    user_agent     TEXT NULL,
    browser        TEXT NULL,
    os             TEXT NULL,
    device         TEXT NULL,
    is_bot         INTEGER NOT NULL DEFAULT 0,
    UNIQUE (visitor_key, bucket_start)
);

CREATE INDEX idx_visitor_event_first_seen
    ON visitor_event (first_seen_at DESC);

CREATE INDEX idx_visitor_event_country_seen
    ON visitor_event (country_name, first_seen_at DESC);

-- ── Swap in new tables ──

DROP TABLE user;
ALTER TABLE user_new RENAME TO user;

DROP TABLE activity;
ALTER TABLE activity_new RENAME TO activity;

DROP TABLE entry;
ALTER TABLE entry_new RENAME TO entry;
