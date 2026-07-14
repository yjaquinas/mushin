-- Rename the "Pro" plan to "Premium"
UPDATE plan_config
SET name = 'Premium',
    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
WHERE plan = 'pro';
