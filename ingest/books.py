"""Public order-book snapshots = your GROUND TRUTH.

This is the file that makes the project defensible. Without it, "your numbers are
made up" is an unanswerable criticism. With it, you have a published error table.

All of these are FREE and need NO API KEY:
  Binance  https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints
  Kraken   https://docs.kraken.com/rest/#tag/Market-Data/operation/getOrderBook
  Coinbase https://docs.cdp.coinbase.com/exchange/reference/exchangerestapi_getproductbook
  OKX      https://www.okx.com/docs-v5/en/#order-book-trading-market-data

Run daily:  python -m ingest.books              # every token in `tokens` listed on a venue
            python -m ingest.books --limit 20   # quick check

What each venue gives (probed 2026-09-22, all reachable from here):
  binance   5000 levels/side, costs 250 of the 6000/min weight budget -> ~2.6s apart
  okx       5000 levels/side (books-full)
  coinbase  the FULL book (level=2) -- never truncated, often 20k+ levels
  kraken    500 levels max -- truncates first for big sizes on liquid pairs

A book that runs out before `size` is filled is a RESULT, not an error -- but only
if we saw the whole book. If the venue capped the levels, we don't know; that row
is 'truncated', never 'thin'. Mixing those up would teach the model that deep
books are shallow.

Order books: https://en.wikipedia.org/wiki/Order_book
"""
import os, sys, json, time, zlib, sqlite3, argparse, threading, datetime as dt
from concurrent.futures import ThreadPoolExecutor
import requests

from .config import DB_PATH

SIZES = (1_000, 10_000, 100_000, 1_000_000, 10_000_000)
PRICE_TOL = 0.10        # venue mid vs CMC's last hourly close; wider = wrong token
RAW_BAND = 0.10         # keep raw levels within 10% of mid, so walks can be recomputed
UA = {"User-Agent": "exit-research/0.1"}


# --- venues -------------------------------------------------------------------
# Each venue: how to list its markets, how to fetch one book, its level cap, its pace.

def _binance_markets():
    j = requests.get("https://api.binance.com/api/v3/exchangeInfo",
                     params={"permissions": "SPOT"}, headers=UA, timeout=30).json()
    return {s["baseAsset"]: s["symbol"] for s in j["symbols"]
            if s["quoteAsset"] == "USDT" and s["status"] == "TRADING"}


def _binance_book(pair):
    j = requests.get("https://api.binance.com/api/v3/depth",
                     params={"symbol": pair, "limit": 5000}, headers=UA, timeout=30).json()
    return j["bids"], j["asks"]


def _okx_markets():
    j = requests.get("https://www.okx.com/api/v5/public/instruments",
                     params={"instType": "SPOT"}, headers=UA, timeout=30).json()
    return {s["baseCcy"]: s["instId"] for s in j["data"]
            if s["quoteCcy"] == "USDT" and s["state"] == "live"}


def _okx_book(pair):
    j = requests.get("https://www.okx.com/api/v5/market/books-full",
                     params={"instId": pair, "sz": 5000}, headers=UA, timeout=30).json()
    d = j["data"][0]
    return d["bids"], d["asks"]


def _coinbase_markets():
    j = requests.get("https://api.exchange.coinbase.com/products", headers=UA, timeout=30).json()
    return {p["base_currency"]: p["id"] for p in j
            if p["quote_currency"] == "USD" and p["status"] == "online"
            and not p.get("trading_disabled")}


def _coinbase_book(pair):
    j = requests.get(f"https://api.exchange.coinbase.com/products/{pair}/book",
                     params={"level": 2}, headers=UA, timeout=30).json()
    return j["bids"], j["asks"]


KRAKEN_ALIASES = {"XBT": "BTC", "XDG": "DOGE"}


def _kraken_markets():
    j = requests.get("https://api.kraken.com/0/public/AssetPairs", headers=UA, timeout=30).json()
    out = {}
    for name, p in j["result"].items():
        base, _, quote = (p.get("wsname") or "").partition("/")
        if quote == "USD" and not name.endswith(".d"):
            out[KRAKEN_ALIASES.get(base, base)] = name
    return out


def _kraken_book(pair):
    j = requests.get("https://api.kraken.com/0/public/Depth",
                     params={"pair": pair, "count": 500}, headers=UA, timeout=30).json()
    if j.get("error"):
        raise RuntimeError(j["error"])
    d = next(iter(j["result"].values()))
    return d["bids"], d["asks"]


# name: (list markets, fetch book, max levels per side or None if full book, seconds between calls, quote)
VENUES = {
    "binance":  (_binance_markets,  _binance_book,  5000, 2.6, "USDT"),
    "okx":      (_okx_markets,      _okx_book,      5000, 0.6,  "USDT"),
    "coinbase": (_coinbase_markets, _coinbase_book, None, 0.25, "USD"),
    "kraken":   (_kraken_markets,   _kraken_book,   500,  1.1, "USD"),
}


def fetch_book(venue: str, pair: str):
    """Return {"bids": [(price, qty), ...], "asks": [...], "truncated": bool},
    best price first, floats. `pair` is the venue's own market id (BTCUSDT, BTC-USD...).

    Each venue nests its response differently -- normalised here so the rest of the
    codebase never knows which exchange a book came from. All four put price and
    size in the first two columns; extra columns (order count, timestamp) are dropped.
    """
    _, fetch, cap, _, _ = VENUES[venue]
    for wait in (3, 10, None):             # OKX resets connections when pushed
        try:
            raw_bids, raw_asks = fetch(pair)
            break
        except requests.RequestException:
            if wait is None:
                raise
            time.sleep(wait)
    bids = sorted(((float(r[0]), float(r[1])) for r in raw_bids if float(r[1]) > 0), reverse=True)
    asks = sorted((float(r[0]), float(r[1])) for r in raw_asks if float(r[1]) > 0)
    truncated = cap is not None and (len(raw_bids) >= cap or len(raw_asks) >= cap)
    return {"bids": bids, "asks": asks, "truncated": truncated}


# --- the walk -----------------------------------------------------------------

def fill_price(levels, size_usd):
    """Average execution price for a market order of `size_usd` notional against
    `levels` (best first). None if the levels run out before it fills."""
    if size_usd <= 0 or not levels:
        return None
    remaining, units = size_usd, 0.0
    for price, qty in levels:
        take = min(remaining, price * qty)       # USD taken at this level
        units += take / price
        remaining -= take
        if remaining <= 1e-9 * size_usd:
            return size_usd / units
    return None


def walk_book(levels, size_usd):
    """TRUE slippage in bps vs the best price, for eating `levels` until `size_usd`
    is filled. Works for both sides: bids for a sell (exit), asks for a buy.
    None when the book is too thin -- that is a RESULT; the caller records it.

    This number is what the model gets graded against.
    """
    avg = fill_price(levels, size_usd)
    if avg is None:
        return None
    best = levels[0][0]
    return 10_000 * abs(best - avg) / best


def depth_within(levels, mid, pct):
    """USD notional resting within `pct` of mid on one side."""
    total = 0.0
    for price, qty in levels:
        if abs(price - mid) / mid > pct:
            break
        total += price * qty
    return total


# --- snapshots ----------------------------------------------------------------

def _universe(db, limit=None):
    """{symbol: (token_id, cmc_price)} for tokens with an unambiguous symbol.
    Price = latest hourly close from the OHLCV backfill, used to catch collisions."""
    rows = db.execute("""
        SELECT t.id, t.symbol,
               (SELECT close FROM ohlcv o WHERE o.token_id = t.id AND o.interval = 'h'
                ORDER BY time_open DESC LIMIT 1),
               (SELECT market_cap FROM ohlcv o WHERE o.token_id = t.id AND o.interval = 'd'
                ORDER BY time_open DESC LIMIT 1)
        FROM tokens t""").fetchall()
    rows.sort(key=lambda r: -(r[3] or 0))
    counts = {}
    for _, sym, _, _ in rows:
        counts[sym] = counts.get(sym, 0) + 1
    out = {sym: (tid, px) for tid, sym, px, _ in rows if counts[sym] == 1}
    skipped = sorted(s for s, c in counts.items() if c > 1)
    if limit:
        out = dict(list(out.items())[:limit])
    return out, skipped


def _snap_venue(venue, targets, sizes, ts, log):
    """Fetch every target book on one venue at that venue's pace. Returns rows."""
    _, _, _, pace, quote = VENUES[venue]
    books, raws = [], []
    for sym, (tid, cmc_px, pair) in targets.items():
        t0 = time.monotonic()
        try:
            b = fetch_book(venue, pair)
        except Exception as e:
            log(f"  {venue:<9} {pair:<12} ERROR {type(e).__name__}: {str(e)[:80]}")
            time.sleep(pace)
            continue
        if not b["bids"] or not b["asks"]:
            continue
        best_bid, best_ask = b["bids"][0][0], b["asks"][0][0]
        mid = (best_bid + best_ask) / 2
        base = dict(ts=ts, token_id=tid, symbol=sym, venue=venue, pair=pair, quote=quote,
                    mid=mid, spread_bps=10_000 * (best_ask - best_bid) / mid,
                    truncated=int(b["truncated"]))

        if cmc_px and abs(mid / cmc_px - 1) > PRICE_TOL:
            # Same ticker, different token (or a dead market). Never walk it.
            books.append(dict(base, side="sell", size_usd=0, slippage_bps=None,
                              impact_mid_bps=None, status="price_mismatch",
                              depth_2pct_usd=None, levels=len(b["bids"])))
            log(f"  {venue:<9} {pair:<12} price_mismatch mid={mid:.6g} cmc={cmc_px:.6g}")
        else:
            for side, levels in (("sell", b["bids"]), ("buy", b["asks"])):
                d2 = depth_within(levels, mid, 0.02)
                for size in sizes:
                    avg = fill_price(levels, size)
                    if avg is None:
                        status = "truncated" if b["truncated"] else "thin"
                        slip = impact = None
                    else:
                        status = "ok"
                        slip = walk_book(levels, size)
                        impact = 10_000 * abs(avg - mid) / mid
                    books.append(dict(base, side=side, size_usd=size, slippage_bps=slip,
                                      impact_mid_bps=impact, status=status,
                                      depth_2pct_usd=d2, levels=len(levels)))
            keep = {k: [lv for lv in b[k] if abs(lv[0] - mid) / mid <= RAW_BAND]
                    for k in ("bids", "asks")}
            raws.append((ts, tid, venue, pair, mid, int(b["truncated"]),
                         zlib.compress(json.dumps(keep, separators=(",", ":")).encode())))
        time.sleep(max(0.0, pace - (time.monotonic() - t0)))
    log(f"  {venue:<9} done: {len(raws)} books")
    return books, raws


def snapshot_all(symbols=None, sizes=SIZES, venues=tuple(VENUES), limit=None, db_path=DB_PATH):
    """Run DAILY from day 2. Writes to `books` (one row per token/venue/side/size)
    and `book_raw` (compressed levels, so a fixed walk can be re-run on old data).

    Venues run in parallel, each at its own rate limit; the slowest (Binance,
    ~2.6s per book) sets the wall time.
    """
    db = sqlite3.connect(db_path)
    with open(os.path.join(os.path.dirname(__file__), "schema.sql")) as f:
        db.executescript(f.read())
    universe, ambiguous = _universe(db, limit)
    if not universe:
        sys.exit("tokens table is empty -- run scripts/backfill_ohlcv.py first.")
    if symbols:
        universe = {s: v for s, v in universe.items() if s in set(symbols)}
    if ambiguous:
        print(f"Skipping symbols shared by 2+ CMC tokens: {', '.join(ambiguous)}")

    ts = dt.datetime.now(dt.timezone.utc).replace(second=0, microsecond=0).isoformat()
    lock = threading.Lock()

    def log(msg):
        with lock:
            print(msg, flush=True)

    plan = {}
    for v in venues:
        try:
            markets = VENUES[v][0]()
        except Exception as e:
            log(f"  {v:<9} market list failed ({type(e).__name__}) -- skipping venue")
            continue
        plan[v] = {s: (tid, px, markets[s]) for s, (tid, px) in universe.items() if s in markets}
        eta = len(plan[v]) * VENUES[v][3]
        log(f"  {v:<9} {len(plan[v]):>4} of {len(universe)} tokens listed  (~{eta / 60:.0f} min)")

    with ThreadPoolExecutor(len(plan) or 1) as ex:
        futures = [ex.submit(_snap_venue, v, t, sizes, ts, log) for v, t in plan.items()]
        results = [f.result() for f in futures]

    cols = ("ts", "token_id", "symbol", "venue", "pair", "quote", "side", "size_usd",
            "slippage_bps", "impact_mid_bps", "status", "mid", "spread_bps",
            "depth_2pct_usd", "levels", "truncated")
    for books, raws in results:
        db.executemany(f"INSERT OR REPLACE INTO books({','.join(cols)}) "
                       f"VALUES ({','.join('?' * len(cols))})",
                       [tuple(r[c] for c in cols) for r in books])
        db.executemany("INSERT OR REPLACE INTO book_raw(ts, token_id, venue, pair, mid, "
                       "truncated, levels_zlib) VALUES (?,?,?,?,?,?,?)", raws)
    db.commit()
    return ts


def _summary(db_path, ts):
    db = sqlite3.connect(db_path)
    print(f"\n=== Snapshot {ts} ===")
    print(f"{'venue':<10}{'books':>7}  {'ok':>6}{'thin':>6}{'trunc':>7}{'mismatch':>10}")
    for v, n, ok, thin, tr, mm in db.execute("""
        SELECT venue, COUNT(DISTINCT token_id),
               SUM(status='ok'), SUM(status='thin'), SUM(status='truncated'),
               SUM(status='price_mismatch')
        FROM books WHERE ts=? GROUP BY venue""", (ts,)):
        print(f"{v:<10}{n:>7}  {ok:>6}{thin:>6}{tr:>7}{mm:>10}")
    print("\nMedian SELL slippage (bps vs best bid) by size, status=ok:")
    for size in SIZES:
        vals = sorted(r[0] for r in db.execute(
            "SELECT slippage_bps FROM books WHERE ts=? AND side='sell' AND size_usd=? "
            "AND status='ok'", (ts, size)))
        med = vals[len(vals) // 2] if vals else None
        print(f"  ${size:>12,}  n={len(vals):<5} median={'-' if med is None else f'{med:.1f}'}")
    tokens = db.execute("SELECT COUNT(DISTINCT token_id) FROM books WHERE ts=? AND status='ok'",
                        (ts,)).fetchone()[0]
    print(f"\n{tokens} tokens with at least one usable book.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Snapshot public order books into `books`.")
    ap.add_argument("--limit", type=int, help="only the top-N tokens by market cap")
    ap.add_argument("--venues", default=",".join(VENUES), help="comma list, default all")
    ap.add_argument("--symbols", help="comma list of symbols, e.g. BTC,ETH")
    a = ap.parse_args()
    ts = snapshot_all(symbols=a.symbols.split(",") if a.symbols else None,
                      venues=tuple(a.venues.split(",")), limit=a.limit)
    _summary(DB_PATH, ts)
