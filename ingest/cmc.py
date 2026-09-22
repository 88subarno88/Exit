"""CoinMarketCap client.

Docs: https://coinmarketcap.com/api/documentation/v1/
Conventions & rate limits:
  https://coinmarketcap.com/api/documentation/v1/#section/Standards-and-Conventions

Three things this client must do beyond fetching:
  1. log every call (endpoint, status, latency, credits, cache hit) -> /debug page
  2. respect the cache -> your credit budget and your post-expiry demo
  3. resolve by CMC id, never symbol
"""

import time
from datetime import datetime, timezone
import requests
from .config import HEADERS, BASE_URL, TTL
from . import cache


def _get(path: str, params: dict, ttl: int):
    """Every request goes through here. Nothing calls requests directly."""
    # Sorting params ensures the cache key is stable regardless of dict insertion order
    key = f"{path}:{sorted(params.items())}"
    fetched = []
    result = cache.cached(key, ttl, lambda: fetched.append(1) or _raw(path, params))
    if not fetched:
        _log(path, 200, 0, 0, cache_hit=1)   # served from cache: 0 credits, still visible on /debug
    return result


def _log(path, status, latency_ms, credits, cache_hit=0):
    """One row in api_calls. Columns must match ingest/schema.sql -- scripts write here too."""
    try:
        conn = cache._conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_calls (
                ts TEXT, endpoint TEXT, status INTEGER,
                latency_ms INTEGER, credits INTEGER, cache_hit INTEGER
            )
        """)
        conn.execute(
            "INSERT INTO api_calls (ts, endpoint, status, latency_ms, credits, cache_hit) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), path, status, latency_ms, credits, cache_hit)
        )
        conn.commit()
    except Exception as e:
        print(f"Warning: Failed to log API call: {e}")


def _raw(path: str, params: dict):
    """The actual HTTP call + logging."""
    url = BASE_URL + path
    max_retries = 3
    for attempt in range(max_retries):
        t0 = time.perf_counter()
        # 20s timeout prevents the worker from hanging if CMC degrades
        r = requests.get(url, headers=HEADERS, params=params, timeout=20)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        
        # Parse CMC's standard envelope: {"status": {...}, "data": {...}}
        try:
            resp_json = r.json()
        except ValueError:
            resp_json = {}     
        status = resp_json.get("status", {})
        credits_used = status.get("credit_count", 0)
        
        # 1. Log every call to api_calls
        _log(path, r.status_code, elapsed_ms, credits_used)

        # 2. Handle 429 Rate Limiting with exponential backoff
        if r.status_code == 429 and attempt < max_retries - 1:
            time.sleep(2 ** attempt)  # Sleep 1s, then 2s
            continue
            
        # 3. Handle standard errors using CMC's internal error_message
        if r.status_code != 200:
            error_message = status.get("error_message") or r.text
            raise Exception(f"CMC API Error {r.status_code} on {path}: {error_message}")
            
        return resp_json.get("data")



def listings(limit=500, sort="volume_24h"):
    """/v1/cryptocurrency/listings/latest — your universe.
    NOTE: limit=5000 is not one credit. Check the credit rules before you widen it."""
    return _get("/v1/cryptocurrency/listings/latest", {"limit": limit, "sort": sort}, TTL["listings"])


def market_pairs(token_id: int, limit=100):
    """/v1/cryptocurrency/market-pairs/latest — THE CORE ENDPOINT.

    One call per token. At 500 tokens that's ~500 calls per full refresh.
    Returns every venue the token trades on. You want, per pair:
        exchange name, pair name, quote volume 24h, price

    These become rows in `pairs`, and `pairs` is what the impact model is built on.
    If this returns thin data, run scripts/day1_validate.py and rethink."""
    return _get("/v1/cryptocurrency/market-pairs/latest", {"id": token_id, "limit": limit}, TTL["market_pairs"])


def quotes(ids: list[int]):
    """/v2/cryptocurrency/quotes/latest — BATCH these. ids=1,2,3 in one call."""
    return _get("/v2/cryptocurrency/quotes/latest", {"id": ",".join(map(str, ids))}, TTL["quotes"])


def ohlcv_historical(token_id: int, days=90):
    """/v2/cryptocurrency/ohlcv/historical — volatility (sigma) + Hindsight.
    TIER-GATED. Check your depth on day one; if it's shallow, Hindsight shrinks."""
    return _get("/v2/cryptocurrency/ohlcv/historical", {
        "id": token_id,
        "time_period": "daily", 
        "count": days
    }, TTL["ohlcv"])


def dex_spot_pairs(**kw):
    """/v4/dex/spot-pairs/latest — on-chain pools. Under-used by everyone else,
    which is exactly why it scores on 'interesting use of the API'."""
    return _get("/v4/dex/spot-pairs/latest", kw, TTL["dex"])