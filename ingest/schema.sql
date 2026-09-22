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

-- Candles from /v2/cryptocurrency/ohlcv/historical. interval: 'd' | 'h'.
-- Filled by scripts/backfill_ohlcv.py. Hourly only reaches back one month on the
-- hackathon plan, so this table is the only place older hourly data will exist.
CREATE TABLE IF NOT EXISTS ohlcv (
    token_id   INTEGER,
    interval   TEXT,
    time_open  TEXT,
    time_close TEXT,
    open       REAL,
    high       REAL,
    low        REAL,
    close      REAL,
    volume     REAL,
    market_cap REAL,
    PRIMARY KEY (token_id, interval, time_open)
);

CREATE TABLE IF NOT EXISTS api_calls (
    ts         TEXT,
    endpoint   TEXT,
    status     INTEGER,
    latency_ms INTEGER,
    credits    INTEGER,
    cache_hit  INTEGER
);

-- Ground truth from public order books (step 4). One row per
-- (snapshot, token, venue, side, size). Written by ingest/books.py.
--   slippage_bps   : avg fill vs BEST price  -- what the model is graded on
--   impact_mid_bps : avg fill vs MID         -- includes half the spread
--   status         : ok | thin (whole book seen, too small) |
--                    truncated (venue capped the levels -- unknown, NOT thin) |
--                    price_mismatch (same ticker, different token; not walked)
CREATE TABLE IF NOT EXISTS books (
    ts             TEXT,
    token_id       INTEGER,
    symbol         TEXT,
    venue          TEXT,
    pair           TEXT,
    quote          TEXT,
    side           TEXT,
    size_usd       REAL,
    slippage_bps   REAL,
    impact_mid_bps REAL,
    status         TEXT,
    mid            REAL,
    spread_bps     REAL,
    depth_2pct_usd REAL,
    levels         INTEGER,
    truncated      INTEGER,
    PRIMARY KEY (ts, token_id, venue, side, size_usd)
);
CREATE INDEX IF NOT EXISTS idx_books_token ON books(token_id, ts);

-- Raw levels within RAW_BAND (50%) of mid, zlib-compressed JSON {"bids": [[p, q]...], "asks": [...]}.
-- If walk_book ever turns out to be wrong, recompute from here instead of losing days.
CREATE TABLE IF NOT EXISTS book_raw (
    ts          TEXT,
    token_id    INTEGER,
    venue       TEXT,
    pair        TEXT,
    mid         REAL,
    truncated   INTEGER,
    levels_zlib BLOB,
    PRIMARY KEY (ts, token_id, venue)
);

-- TODO(you): add these as you reach each step.
--   liquidity(token_id, ts, pair_count, hhi, turnover, venue_breadth, score, grade)
--   impact(token_id, ts, Y, max_position_2pct, cost_curve_json, confidence_lo, confidence_hi)
--   api_calls(ts, endpoint, status, latency_ms, credits, cache_hit)  -- powers /debug

-- Why api_calls matters: the hackathon requires "visible evidence of a real API call".
-- A live log page satisfies that better than a README snippet. Build it on day one
-- and you get the requirement for free.
