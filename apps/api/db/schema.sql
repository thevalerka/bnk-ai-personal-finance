-- Attention engine schema (docs/PLAN.md section 4). Applied idempotently at
-- API startup (app/db.py:init_schema) — no separate migration step for a
-- schema this small; revisit with a real migration tool if it outgrows one
-- file (see docs/DECISIONS.md).

CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- NULL for an organic anonymous profile; set to a config/personas/*.yaml
    -- name for a seeded "View as" profile.
    persona TEXT
);

-- Raw event log — the "source events" the explain panel cites. Retained in
-- full for now; docs/PLAN.md's 30-day compaction job is deferred (not part
-- of the P3 DoD — see docs/STATE.md).
CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    profile_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    -- Dotted taxonomy leaf id, e.g. "equities.us_large_cap.technology"
    -- (app/attention/taxonomy.py). Always a leaf; decay.propagate() derives
    -- the bucket/asset_class contributions from it.
    node_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    weight DOUBLE PRECISION NOT NULL,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Free-form context for the explain panel (e.g. which instrument/symbol
    -- triggered it, dwell seconds) — never used for scoring itself.
    meta JSONB
);
CREATE INDEX IF NOT EXISTS events_profile_ts_idx ON events (profile_id, ts DESC);
CREATE INDEX IF NOT EXISTS events_profile_node_idx ON events (profile_id, node_id);

-- One row per (profile, DAG node) at ANY level (leaf node, bucket, or asset
-- class — all share the same dotted-id namespace). `score`/`last_updated`
-- are the decay-on-read pair from app/attention/decay.py: decay forward to
-- "now" at read time rather than replaying event history.
CREATE TABLE IF NOT EXISTS interest_scores (
    profile_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    node_id TEXT NOT NULL,
    score DOUBLE PRECISION NOT NULL DEFAULT 0,
    last_updated TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Set by an explicit MUTE event; caps the node's effective score
    -- (decay.MUTE_CEILING) until a PIN on the same node clears it.
    muted BOOLEAN NOT NULL DEFAULT false,
    PRIMARY KEY (profile_id, node_id)
);
