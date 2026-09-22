"""Rate every token once per run, and keep the history -- the downgrade feed is a
diff between consecutive runs.

Run:  python -m ingest.ratings          (daily.sh does this after calibrating)

Inputs per token, the same as calibration used: the last complete daily candle's
volume, 30 days of closes for sigma. Only tokens with a candle in the last 3 days
are rated -- a stale rating is worse than none.
"""
import os, sqlite3, datetime as dt

from .config import DB_PATH
from .books import fill_price, SIZES
from .calibrate import _consolidated_books
from .impact import (sigma_daily, max_position, exit_cost, manipulation_cost, grade,
                     band_max_position, CALIBRATED_MAX_USD, Y_DEFAULT, DELTA)

FRESH_DAYS = 3
WINDOW = 30


def compute(db):
    ts = dt.datetime.now(dt.timezone.utc).replace(second=0, microsecond=0).isoformat()
    cutoff = (dt.date.today() - dt.timedelta(days=FRESH_DAYS)).isoformat()
    tokens = db.execute("SELECT id, symbol, name, slug FROM tokens").fetchall()
    out = []
    for tid, sym, name, slug in tokens:
        c = db.execute("SELECT time_open, close, volume, market_cap FROM ohlcv "
                       "WHERE token_id=? AND interval='d' ORDER BY time_open DESC LIMIT ?",
                       (tid, WINDOW + 1)).fetchall()[::-1]
        if not c or c[-1][0][:10] < cutoff:
            continue
        _, price, vol, mcap = c[-1]
        sig = sigma_daily([x[1] for x in c])
        mp = max_position(vol, sig)
        band = band_max_position(mp)
        ec = exit_cost(100_000, vol, sig)
        mc = manipulation_cost(vol, sig)
        out.append((ts, tid, sym, name, slug, price, mcap, vol, sig, Y_DEFAULT, DELTA, mp,
                    band[0] if band else None, band[1] if band else None,
                    int(mp is not None and mp > CALIBRATED_MAX_USD), grade(mp),
                    ec["bps"] if ec else None, mc["cost_usd"] if mc else None))
    db.executemany(f"INSERT OR REPLACE INTO ratings VALUES ({','.join('?' * 18)})", out)
    observed(db)
    db.commit()
    return ts, len(out)


def observed(db):
    """Walk today's merged books at every size -- the dots the token page plots
    against the model curve. Same walk as calibrate.py."""
    books = _consolidated_books(db)
    if not books:
        return
    day = max(d for _, d in books)
    rows = []
    for (tid, d), b in books.items():
        if d != day or not b["bids"] or not b["asks"]:
            continue
        mid = (b["bids"][0][0] + b["asks"][0][0]) / 2
        for size in SIZES:
            avg = fill_price(b["bids"], size)
            if avg is None:
                if not b["truncated"]:
                    rows.append((day, tid, size, None, "unabsorbable", b["venues"]))
                continue
            rows.append((day, tid, size, max(10_000 * (mid - avg) / mid, 0.0), "ok", b["venues"]))
    db.executemany("INSERT OR REPLACE INTO observed_costs VALUES (?,?,?,?,?,?)", rows)


def feed(db, limit=50):
    """Grade changes between each token's consecutive runs, newest first."""
    return db.execute("""
        SELECT r.ts, r.symbol, r.slug, p.grade AS old, r.grade AS new, r.max_position
        FROM ratings r
        JOIN ratings p ON p.token_id = r.token_id
         AND p.ts = (SELECT MAX(ts) FROM ratings WHERE token_id = r.token_id AND ts < r.ts)
        WHERE p.grade != r.grade
        ORDER BY r.ts DESC, r.market_cap DESC LIMIT ?""", (limit,)).fetchall()


if __name__ == "__main__":
    db = sqlite3.connect(DB_PATH)
    with open(os.path.join(os.path.dirname(__file__), "schema.sql")) as f:
        db.executescript(f.read())
    ts, n = compute(db)
    print(f"Rated {n} tokens at {ts}. Grade changes since the previous run: {len(feed(db))}")
