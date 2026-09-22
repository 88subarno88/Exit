-- Run once: sqlite3 data/exit.db < ingest/schema.sql
-- Learn: https://docs.python.org/3/library/sqlite3.html

-- Token universe. Keyed by CMC id, NEVER by symbol.
-- Symbols collide across tokens and will silently corrupt every downstream number.
CREATE TABLE IF NOT EXISTS tokens (
    id        INTEGER PRIMARY KEY,   -- CMC id
    symbol    TEXT,
    name      TEXT,
    slug      TEXT,
    sector    TEXT,
    first_seen TEXT
);

-- Point-in-time market state. Accumulates history — this is why you start the
-- worker early. Without rows here you have no charts and no downgrade feed.
CREATE TABLE IF NOT EXISTS snapshots (
    token_id   INTEGER,
    ts         TEXT,
    price      REAL,
    mcap       REAL,
    vol_24h    REAL,
    circ_supply REAL,
    PRIMARY KEY (token_id, ts)
);

-- One row per (token, venue, pair). The edge list. This is the core of the project.
CREATE TABLE IF NOT EXISTS pairs (
    token_id   INTEGER,
    ts         TEXT,
    venue      TEXT,
    venue_type TEXT,          -- 'cex' | 'dex'
    pair       TEXT,
    price      REAL,
    volume_24h REAL
);
CREATE INDEX IF NOT EXISTS idx_pairs_token_ts ON pairs(token_id, ts);

-- TODO(you): add these as you reach each step.
--   liquidity(token_id, ts, pair_count, hhi, turnover, venue_breadth, score, grade)
--   books(symbol, venue, ts, size_usd, true_slippage_bps)   -- ground truth, step 4
--   impact(token_id, ts, Y, max_position_2pct, cost_curve_json, confidence_lo, confidence_hi)
--   api_calls(ts, endpoint, status, latency_ms, credits, cache_hit)  -- powers /debug

-- Why api_calls matters: the hackathon requires "visible evidence of a real API call".
-- A live log page satisfies that better than a README snippet. Build it on day one
-- and you get the requirement for free.
