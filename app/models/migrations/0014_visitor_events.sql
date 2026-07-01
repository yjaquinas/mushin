-- Deduplicated visitor analytics.
-- One row represents one visitor fingerprint within a two-hour bucket.

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
