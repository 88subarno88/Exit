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
import requests
from .config import HEADERS, BASE_URL, TTL
from . import cache


def _get(path: str, params: dict, ttl: int):
    """Every request goes through here. Nothing calls requests directly."""
    # Sorting params ensures the cache key is stable regardless of dict insertion order
    key = f"{path}:{sorted(params.items())}"
    return cache.cached(key, ttl, lambda: _raw(path, params))


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
        
        # 1. Log every call to api_calls (creates table safely if missing)
        try:
            conn = cache._conn()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_calls (
                    path TEXT, 
                    status_code INTEGER, 
                    elapsed_ms INTEGER, 
                    credits INTEGER, 
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute(
                "INSERT INTO api_calls (path, status_code, elapsed_ms, credits) VALUES (?, ?, ?, ?)",
                (path, r.status_code, elapsed_ms, credits_used)
            )
            conn.commit()
        except Exception as e:
            print(f"Warning: Failed to log API call: {e}")

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
    return _get("/v1/cryptocurrency/listings/latest", {"limit": limit, "sort": sort}, TTL)


def market_pairs(token_id: int, limit=100):
    """/v1/cryptocurrency/market-pairs/latest — THE CORE ENDPOINT.

    One call per token. At 500 tokens that's ~500 calls per full refresh.
    Returns every venue the token trades on. You want, per pair:
        exchange name, pair name, quote volume 24h, price

    These become rows in `pairs`, and `pairs` is what the impact model is built on.
    If this returns thin data, run scripts/day1_validate.py and rethink."""
    return _get("/v1/cryptocurrency/market-pairs/latest", {"id": token_id, "limit": limit}, TTL)


def quotes(ids: list[int]):
    """/v2/cryptocurrency/quotes/latest — BATCH these. ids=1,2,3 in one call."""
    return _get("/v2/cryptocurrency/quotes/latest", {"id": ",".join(map(str, ids))}, TTL)


def ohlcv_historical(token_id: int, days=90):
    """/v2/cryptocurrency/ohlcv/historical — volatility (sigma) + Hindsight.
    TIER-GATED. Check your depth on day one; if it's shallow, Hindsight shrinks."""
    return _get("/v2/cryptocurrency/ohlcv/historical", {
        "id": token_id,
        "time_period": "daily", 
        "count": days
    }, TTL)


def dex_spot_pairs(**kw):
    """/v4/dex/spot-pairs/latest — on-chain pools. Under-used by everyone else,
    which is exactly why it scores on 'interesting use of the API'."""
    return _get("/v4/dex/spot-pairs/latest", kw, TTL)