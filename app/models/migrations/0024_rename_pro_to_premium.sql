-- Rename internal plan identifier from 'pro' to 'premium'
UPDATE plan_config SET plan = 'premium', updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE plan = 'pro';
UPDATE user SET plan = 'premium' WHERE plan = 'pro';
UPDATE payment SET plan = 'premium' WHERE plan = 'pro';
