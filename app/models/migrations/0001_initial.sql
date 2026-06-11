-- 0001_initial.sql
-- Full Mushin schema — all tables land here so later phases build on a stable foundation.
-- WAL + foreign_keys are enabled by the connection layer, not here.

CREATE TABLE user (
    id               INTEGER PRIMARY KEY,
    auth_provider    TEXT    NOT NULL CHECK (auth_provider IN ('kakao', 'google', 'email', 'guest')),
    provider_id      TEXT    NULL,
    password_hash    TEXT    NULL,
    display_name     TEXT    NULL,
    created_at       TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_active_at   TEXT    NULL
);

CREATE TABLE category (
    id           INTEGER PRIMARY KEY,
    owner_id     INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    name         TEXT    NOT NULL,
    color        TEXT    NULL,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    archived_at  TEXT    NULL,
    created_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sub_tally (
    id             INTEGER PRIMARY KEY,
    owner_id       INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    category_id    INTEGER NOT NULL REFERENCES category(id) ON DELETE CASCADE,
    name           TEXT    NOT NULL,
    count_mode     TEXT    NOT NULL CHECK (count_mode IN ('running', 'progression')),
    config_json    TEXT    NULL,
    cached_count   INTEGER NOT NULL DEFAULT 0,
    cached_streak  INTEGER NOT NULL DEFAULT 0,
    last_entry_at  TEXT    NULL,
    sort_order     INTEGER NOT NULL DEFAULT 0,
    archived_at    TEXT    NULL,
    created_at     TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE field_def (
    id           INTEGER PRIMARY KEY,
    sub_tally_id INTEGER NOT NULL REFERENCES sub_tally(id) ON DELETE CASCADE,
    kind         TEXT    NOT NULL CHECK (kind IN ('tag_group', 'scale', 'count', 'memo', 'match_list', 'level', 'result')),
    label        TEXT    NOT NULL,
    config_json  TEXT    NULL,
    sort_order   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE tag (
    id           INTEGER PRIMARY KEY,
    owner_id     INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    field_def_id INTEGER NOT NULL REFERENCES field_def(id) ON DELETE CASCADE,
    name         TEXT    NOT NULL,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    archived_at  TEXT    NULL,
    created_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE entry (
    id           INTEGER PRIMARY KEY,
    owner_id     INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    sub_tally_id INTEGER NOT NULL REFERENCES sub_tally(id) ON DELETE CASCADE,
    occurred_at  TEXT    NOT NULL,
    memo         TEXT    NULL,
    created_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE entry_tag (
    entry_id INTEGER NOT NULL REFERENCES entry(id) ON DELETE CASCADE,
    tag_id   INTEGER NOT NULL REFERENCES tag(id) ON DELETE CASCADE,
    PRIMARY KEY (entry_id, tag_id)
);

CREATE TABLE entry_value (
    entry_id     INTEGER NOT NULL REFERENCES entry(id) ON DELETE CASCADE,
    field_def_id INTEGER NOT NULL REFERENCES field_def(id) ON DELETE CASCADE,
    num_value    REAL    NULL,
    text_value   TEXT    NULL,
    PRIMARY KEY (entry_id, field_def_id),
    CHECK (num_value IS NOT NULL OR text_value IS NOT NULL)
);

CREATE TABLE match (
    id         INTEGER PRIMARY KEY,
    entry_id   INTEGER NOT NULL REFERENCES entry(id) ON DELETE CASCADE,
    owner_id   INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    opponent   TEXT    NOT NULL,
    score      TEXT    NOT NULL,
    result     TEXT    NOT NULL CHECK (result IN ('win', 'loss', 'draw')),
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE level (
    id           INTEGER PRIMARY KEY,
    sub_tally_id INTEGER NOT NULL REFERENCES sub_tally(id) ON DELETE CASCADE,
    owner_id     INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    track        TEXT    NOT NULL,
    ordinal      INTEGER NOT NULL,
    code         TEXT    NOT NULL,
    label        TEXT    NOT NULL,
    archived_at  TEXT    NULL
);

CREATE TABLE level_rule (
    id              INTEGER PRIMARY KEY,
    owner_id        INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    sub_tally_id    INTEGER NOT NULL REFERENCES sub_tally(id) ON DELETE CASCADE,
    from_level_id   INTEGER NULL     REFERENCES level(id) ON DELETE CASCADE,
    to_level_id     INTEGER NOT NULL REFERENCES level(id) ON DELETE CASCADE,
    gate_type       TEXT    NOT NULL CHECK (gate_type IN ('time', 'count', 'event', 'manual')),
    gate_value      REAL    NULL,
    min_age         INTEGER NULL,
    prereq_level_id INTEGER NULL     REFERENCES level(id) ON DELETE SET NULL
);

-- Indexes

-- Entry list and stats range scan (the primary hot path)
CREATE INDEX idx_entry_subtally_time
    ON entry (sub_tally_id, occurred_at DESC);

-- Active sub-tallies by category
CREATE INDEX idx_sub_tally_category_active
    ON sub_tally (category_id)
    WHERE archived_at IS NULL;

-- Active categories by owner
CREATE INDEX idx_category_owner_active
    ON category (owner_id)
    WHERE archived_at IS NULL;

-- Match lookup by entry
CREATE INDEX idx_match_entry
    ON match (entry_id);

-- Level ordered lookup (progression query)
CREATE INDEX idx_level_subtally_track_ordinal
    ON level (sub_tally_id, track, ordinal);

-- Guest-reaper scan (purge inactive guests)
CREATE INDEX idx_user_guest_last_active
    ON user (last_active_at)
    WHERE auth_provider = 'guest';
