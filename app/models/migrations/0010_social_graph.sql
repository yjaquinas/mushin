-- 0010_social_graph.sql
-- Social graph (Phase: fellows): mutual connections + one-directional blocks,
-- plus the re-consent flag for existing private users gaining a character
-- sheet under the new three-tier visibility model.
--
-- connection is the directed handshake (requester -> addressee) for a mutual
-- "fellow" relationship. A canonical directionless pair (user_lo, user_hi),
-- computed by the service layer as (MIN(a,b), MAX(a,b)), is uniquely indexed
-- so A->B and B->A can never both exist -- a re-request after a decline reuses
-- the same row rather than creating a duplicate pair.
--
-- sharing_consent_at is distinct from status='accepted': it is stamped only
-- when the addressee confirms the deliberate consequence screen, and is the
-- bit that actually gates private-note exposure (see profiles.py, a later
-- task). "Accepted but not yet consented" is a valid, queryable state.

CREATE TABLE connection (
    id                  INTEGER PRIMARY KEY,
    requester_id        INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    addressee_id        INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    status              TEXT    NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'declined')),
    user_lo             INTEGER NOT NULL,
    user_hi             INTEGER NOT NULL,
    sharing_consent_at  TEXT    NULL,
    created_at          TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    responded_at        TEXT    NULL,
    CHECK (requester_id <> addressee_id),
    CHECK (user_lo < user_hi)
);

-- Canonical-pair uniqueness guard: A->B and B->A collide on (user_lo, user_hi).
CREATE UNIQUE INDEX ux_connection_pair
    ON connection (user_lo, user_hi);

-- Incoming requests for a given addressee (pending inbox, accepted list, etc).
CREATE INDEX idx_connection_addressee_status
    ON connection (addressee_id, status);

-- "My connections" lookups from either side of the canonical pair.
CREATE INDEX idx_connection_lo_status
    ON connection (user_lo, status);

CREATE INDEX idx_connection_hi_status
    ON connection (user_hi, status);

-- block is one-directional and silent -- indistinguishable from
-- non-existence to the blocked party (no existence oracle).
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

-- One-time re-consent gate: existing private users must see and acknowledge
-- the new three-tier visibility explainer (character sheet replaces the old
-- "private = hidden stub") before it takes effect on their account. Distinct
-- from user.consent_seen_at (migration 0005), which covers the original
-- public/private explainer.
ALTER TABLE user ADD COLUMN private_redefinition_seen_at TEXT NULL;
