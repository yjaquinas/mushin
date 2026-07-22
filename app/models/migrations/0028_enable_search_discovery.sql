-- Enable search-engine discovery for every existing account. Owners can turn
-- this setting off at any time from Settings.
UPDATE user
SET search_discovery = 1,
    search_discovery_updated_at = CURRENT_TIMESTAMP;
