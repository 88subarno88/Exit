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

-- One row per token per daily run. Written by ingest/ratings.py; everything the
-- site shows about a token comes from here. Grade changes between runs = the
-- downgrade feed.
CREATE TABLE IF NOT EXISTS ratings (
    ts              TEXT,
    token_id        INTEGER,
    symbol          TEXT,
    name            TEXT,
    slug            TEXT,
    price           REAL,
    market_cap      REAL,
    volume_24h      REAL,
    sigma           REAL,
    Y               REAL,
    delta           REAL,
    max_position    REAL,
    max_pos_lo      REAL,
    max_pos_hi      REAL,
    extrapolated    INTEGER,
    grade           TEXT,
    exit_100k_bps   REAL,
    manip_10pct_usd REAL,
    PRIMARY KEY (ts, token_id)
);
CREATE INDEX IF NOT EXISTS idx_ratings_token ON ratings(token_id, ts);

-- Hindsight (ingest/hindsight.py): raw candles for past collapses, and the
-- same daily rating the live site uses, run over them.
CREATE TABLE IF NOT EXISTS hindsight_candles (
    case_key   TEXT,
    token_id   INTEGER,
    day        TEXT,
    close      REAL,
    volume     REAL,
    market_cap REAL,
    PRIMARY KEY (case_key, day)
);
CREATE TABLE IF NOT EXISTS hindsight (
    case_key      TEXT,
    day           TEXT,
    close         REAL,
    volume        REAL,
    market_cap    REAL,
    sigma         REAL,
    max_position  REAL,
    grade         TEXT,
    exit_100k_bps REAL,
    PRIMARY KEY (case_key, day)
);

-- The evidence on each token page: cost of an immediate sale into the merged
-- order books, per size, for the latest day. status: ok | unabsorbable.
CREATE TABLE IF NOT EXISTS observed_costs (
    day      TEXT,
    token_id INTEGER,
    size_usd REAL,
    bps      REAL,
    status   TEXT,
    venues   INTEGER,
    PRIMARY KEY (day, token_id, size_usd)
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- Why api_calls matters: the hackathon requires "visible evidence of a real API call".
-- A live log page satisfies that better than a README snippet. Build it on day one
-- and you get the requirement for free.
