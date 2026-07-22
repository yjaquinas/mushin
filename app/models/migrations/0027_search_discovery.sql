-- Search-engine discovery is separate from profile visibility. New accounts
-- are discoverable by default; the owner can disable it in Settings.
ALTER TABLE user ADD COLUMN search_discovery INTEGER NOT NULL DEFAULT 1
    CHECK (search_discovery IN (0, 1));
ALTER TABLE user ADD COLUMN search_discovery_updated_at TEXT NULL;
