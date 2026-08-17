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

-- Hyperliquid trading (docs/DECISIONS.md ADR-0028). Both tables are a
-- record of what the wallet already did directly against Hyperliquid
-- (client-side signed, testnet) — the backend never signs or holds a key,
-- it only logs confirmed activity for the operator's own commission
-- accounting. wallet_address is always lower-cased before storage/lookup.

CREATE TABLE IF NOT EXISTS builder_approvals (
    id BIGSERIAL PRIMARY KEY,
    wallet_address TEXT NOT NULL,
    max_fee_tenths_bp INTEGER NOT NULL,
    approved_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS builder_approvals_wallet_idx ON builder_approvals (wallet_address);

CREATE TABLE IF NOT EXISTS order_fills (
    id BIGSERIAL PRIMARY KEY,
    wallet_address TEXT NOT NULL,
    coin TEXT NOT NULL,
    side TEXT NOT NULL,
    size DOUBLE PRECISION NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    builder_fee_tenths_bp INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS order_fills_wallet_ts_idx ON order_fills (wallet_address, created_at DESC);

-- Jupiter (jup.ag) xStocks swaps + Jupiter Lend stablecoin deposits/
-- withdrawals (docs/DECISIONS.md ADR-0029). Same role as the two tables
-- above: a record of what the wallet already did directly on Solana
-- mainnet (client-side signed) — the backend never signs or holds a key,
-- it only logs a claimed action after re-verifying the signature actually
-- landed on-chain (app/jupiter/solana_verify.py).

CREATE TABLE IF NOT EXISTS dex_swaps (
    id BIGSERIAL PRIMARY KEY,
    wallet_address TEXT NOT NULL,
    input_mint TEXT NOT NULL,
    output_mint TEXT NOT NULL,
    in_amount TEXT NOT NULL,
    out_amount TEXT NOT NULL,
    signature TEXT NOT NULL UNIQUE,
    platform_fee_bps INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS dex_swaps_wallet_ts_idx ON dex_swaps (wallet_address, created_at DESC);

CREATE TABLE IF NOT EXISTS lend_positions (
    id BIGSERIAL PRIMARY KEY,
    wallet_address TEXT NOT NULL,
    asset_mint TEXT NOT NULL,
    action TEXT NOT NULL,
    amount TEXT NOT NULL,
    signature TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS lend_positions_wallet_ts_idx ON lend_positions (wallet_address, created_at DESC);
