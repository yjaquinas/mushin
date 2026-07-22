-- Search-engine discovery is separate from profile visibility.  Existing and
-- newly created accounts remain opted out until the owner explicitly opts in.
ALTER TABLE user ADD COLUMN search_discovery INTEGER NOT NULL DEFAULT 0
    CHECK (search_discovery IN (0, 1));
ALTER TABLE user ADD COLUMN search_discovery_updated_at TEXT NULL;
