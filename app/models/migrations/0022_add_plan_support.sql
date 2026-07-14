-- Add plan support: plan_config, user.plan column, payment table

CREATE TABLE plan_config (
    id                  INTEGER PRIMARY KEY,
    plan                TEXT    NOT NULL UNIQUE,
    name                TEXT    NOT NULL,
    max_activities      INTEGER NOT NULL DEFAULT 3,
    max_entries_per_date INTEGER NOT NULL DEFAULT 1,
    secret_activities   INTEGER NOT NULL DEFAULT 0,
    price_monthly       INTEGER,
    price_yearly        INTEGER,
    created_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

INSERT INTO plan_config (plan, name, max_activities, max_entries_per_date, secret_activities, price_monthly)
VALUES ('basic', 'Basic', 3, 1, 0, NULL),
       ('pro', 'Pro', 20, 10, 1, 0);

ALTER TABLE user ADD COLUMN plan TEXT NOT NULL DEFAULT 'basic';

CREATE TABLE payment (
    id                  INTEGER PRIMARY KEY,
    user_id             INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    plan                TEXT    NOT NULL,
    amount_cents        INTEGER NOT NULL,
    currency            TEXT    NOT NULL DEFAULT 'usd',
    status              TEXT    NOT NULL DEFAULT 'completed'
                        CHECK (status IN ('pending', 'completed', 'refunded', 'failed')),
    payment_method      TEXT,
    payment_provider_id TEXT,
    period_start        TEXT,
    period_end          TEXT,
    created_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX idx_payment_user ON payment(user_id, created_at DESC);
