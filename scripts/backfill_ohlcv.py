#!/usr/bin/env python3
"""One-off OHLCV backfill into SQLite. Run it NOW, and again just before 30 Sep.

Run:  python scripts/backfill_ohlcv.py              # top UNIVERSE_SIZE tokens
      python scripts/backfill_ohlcv.py --limit 20   # try it small first

Why: hackathon access reverts to Basic when submissions close, and judging runs
after that. Whatever history you need for sigma and Hindsight has to be in the
DB before then.

What this plan gives (probed 2026-09-22):
  * daily  -- full history (back to 2013 for BTC). We take DAILY_START onwards.
  * hourly -- ONLY THE LAST MONTH, rolling ("Your plan allows 1 months of
    historical access"). Every day you don't run this, a day of hourly data is
    gone for good. Re-running is incremental and safe.
  * hourly candles need time_period=hourly AND interval=hourly; time_period
    alone still returns one candle per day.
  * cost: 1 credit per 100 candles, summed over all ids in the call. Batching
    ids saves calls, not credits.

Incremental: each run starts from the last candle already stored per token, so
re-runs only pay for new candles. Every call is logged to api_calls.
"""
import os, sys, time, math, sqlite3, argparse, datetime as dt
import requests
from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("CMC_API_KEY")
BASE = os.getenv("CMC_BASE_URL", "https://pro-api.coinmarketcap.com")
DB_PATH = os.getenv("DB_PATH", "data/exit.db")
UNIVERSE = int(os.getenv("UNIVERSE_SIZE", "500"))
if not KEY:
    sys.exit("No CMC_API_KEY. Copy .env.example to .env and add your key.")

H = {"X-CMC_PRO_API_KEY": KEY, "Accept": "application/json"}
SCHEMA = os.path.join(os.path.dirname(__file__), "..", "ingest", "schema.sql")

DAILY_START = dt.date(2024, 1, 1)
HOURLY_MAX = 720          # 30 days; the plan's window is one calendar month
BATCH = 10                # ids per call

UTC = dt.timezone.utc


def connect():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    with open(SCHEMA) as f:
        db.executescript(f.read())
    return db


def get(db, path, params):
    """GET, log to api_calls, return (data, credits) or (None, credits)."""
    t0 = time.perf_counter()
    try:
        r = requests.get(BASE + path, headers=H, params=params, timeout=60)
        body = r.json()
    except Exception as e:
        print(f"  [ERR] {path} {e}")
        return None, 0
    ms = (time.perf_counter() - t0) * 1000
    st = body.get("status", {})
    cr = st.get("credit_count") or 0
    db.execute("INSERT INTO api_calls(ts, endpoint, status, latency_ms, credits, cache_hit) "
               "VALUES (?,?,?,?,?,0)",
               (dt.datetime.now(UTC).isoformat(), path, r.status_code, round(ms), cr))
    if r.status_code != 200 or st.get("error_code") not in (0, "0", None):
        print(f"  [{r.status_code}] {path} ERROR: {st.get('error_message')}")
        return None, cr
    return body.get("data"), cr


def by_id(data):
    """ohlcv/historical returns {"id": ..., "quotes": [...]} for one id and
    {"<id>": {...}} (sometimes {"<id>": [{...}]}) for several. Normalise."""
    if not data:
        return {}
    if "quotes" in data:
        return {int(data["id"]): data["quotes"]}
    out = {}
    for k, v in data.items():
        v = v[0] if isinstance(v, list) and v else v
        out[int(k)] = (v or {}).get("quotes") or [] if isinstance(v, dict) else []
    return out


def store(db, interval, token_id, quotes):
    rows = []
    for q in quotes:
        u = (q.get("quote") or {}).get("USD") or {}
        if u.get("close") is None:
            continue
        rows.append((token_id, interval, q["time_open"], q.get("time_close"),
                     u.get("open"), u.get("high"), u.get("low"), u.get("close"),
                     u.get("volume"), u.get("market_cap")))
    db.executemany("INSERT OR REPLACE INTO ohlcv(token_id, interval, time_open, time_close, "
                   "open, high, low, close, volume, market_cap) VALUES (?,?,?,?,?,?,?,?,?,?)",
                   rows)
    return len(rows)


def last_stored(db, interval, ids):
    q = f"SELECT token_id, MAX(time_open) FROM ohlcv WHERE interval=? AND token_id IN " \
        f"({','.join('?' * len(ids))}) GROUP BY token_id"
    got = dict(db.execute(q, (interval, *ids)).fetchall())
    return {i: got.get(i) for i in ids}


def parse(ts):
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def run(db, tokens):
    ids = [t["id"] for t in tokens]
    now = dt.datetime.now(UTC)
    totals = {"d": 0, "h": 0}
    credits = 0

    for n, i in enumerate(range(0, len(ids), BATCH)):
        batch = ids[i:i + BATCH]

        # --- daily: from the oldest "last stored" in the batch (or DAILY_START) to now
        last = last_stored(db, "d", batch)
        starts = [parse(v).date() + dt.timedelta(days=1) if v else DAILY_START
                  for v in last.values()]
        start = min(starts)
        if start < now.date():
            data, cr = get(db, "/v2/cryptocurrency/ohlcv/historical", {
                "id": ",".join(map(str, batch)), "time_period": "daily", "interval": "daily",
                "time_start": start.isoformat(), "time_end": now.date().isoformat(),
                "convert": "USD"})
            credits += cr
            for tid, quotes in by_id(data).items():
                totals["d"] += store(db, "d", tid, quotes)

        # --- hourly: count back from now; the API won't go past one month anyway
        last = last_stored(db, "h", batch)
        need = [HOURLY_MAX if v is None else
                math.ceil((now - parse(v)).total_seconds() / 3600) for v in last.values()]
        count = min(HOURLY_MAX, max(need))
        if count > 1:
            data, cr = get(db, "/v2/cryptocurrency/ohlcv/historical", {
                "id": ",".join(map(str, batch)), "time_period": "hourly", "interval": "hourly",
                "count": count, "convert": "USD"})
            credits += cr
            for tid, quotes in by_id(data).items():
                totals["h"] += store(db, "h", tid, quotes)

        db.commit()
        done = min(i + BATCH, len(ids))
        print(f"  {done:>4}/{len(ids)}  daily+={totals['d']:<7} hourly+={totals['h']:<7} "
              f"credits={credits}")
        time.sleep(0.2)
    return totals, credits


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=UNIVERSE,
                    help=f"top-N tokens by market cap (default UNIVERSE_SIZE={UNIVERSE})")
    args = ap.parse_args()

    db = connect()
    print(f"=== Universe: top {args.limit} by market cap ===")
    data, cr = get(db, "/v1/cryptocurrency/listings/latest",
                   {"limit": args.limit, "sort": "market_cap", "convert": "USD"})
    if not data:
        sys.exit("listings failed -- check the key and your plan.")
    today = dt.date.today().isoformat()
    db.executemany("INSERT OR IGNORE INTO tokens(id, symbol, name, slug, first_seen) "
                   "VALUES (?,?,?,?,?)",
                   [(t["id"], t["symbol"], t["name"], t["slug"], today) for t in data])
    db.commit()

    est_d = sum(1 for _ in data) * (dt.date.today() - DAILY_START).days
    print(f"  {len(data)} tokens. First run costs about "
          f"{math.ceil(est_d / 100) + math.ceil(len(data) * HOURLY_MAX / 100):,} credits; "
          f"re-runs only pay for new candles.")

    print("\n=== Backfill (daily since %s, hourly last %dh) ===" % (DAILY_START, HOURLY_MAX))
    totals, credits = run(db, data)

    print("\n=== Stored ===")
    for interval, label in (("d", "daily"), ("h", "hourly")):
        n, toks, lo, hi = db.execute(
            "SELECT COUNT(*), COUNT(DISTINCT token_id), MIN(time_open), MAX(time_open) "
            "FROM ohlcv WHERE interval=?", (interval,)).fetchone()
        print(f"  {label:<7} {n:>9,} candles  {toks:>4} tokens  {lo} -> {hi}")
    empty = db.execute("SELECT COUNT(*) FROM tokens t WHERE NOT EXISTS "
                       "(SELECT 1 FROM ohlcv o WHERE o.token_id=t.id)").fetchone()[0]
    if empty:
        print(f"  {empty} tokens have no candles at all (usually brand-new listings).")
    print(f"\nThis run: +{totals['d']:,} daily, +{totals['h']:,} hourly, {credits + cr} credits.")
    print("Hourly history only reaches back one month -- re-run before 30 Sep to extend it.")


if __name__ == "__main__":
    main()
