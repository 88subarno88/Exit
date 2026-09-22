"""CoinMarketCap client.

Docs: https://coinmarketcap.com/api/documentation/v1/
Conventions & rate limits:
  https://coinmarketcap.com/api/documentation/v1/#section/Standards-and-Conventions

Three things this client must do beyond fetching:
  1. log every call (endpoint, status, latency, credits, cache hit) -> /debug page
  2. respect the cache -> your credit budget and your post-expiry demo
  3. resolve by CMC id, never symbol
"""

# import time, requests
# from .config import HEADERS, BASE_URL, TTL
# from . import cache


# def _get(path: str, params: dict, ttl: int):
#     """Every request goes through here. Nothing calls requests directly.
#
#     TODO:
#       key = f"{path}:{sorted(params.items())}"
#       return cache.cached(key, ttl, lambda: _raw(path, params))
#     """
#     ...


# def _raw(path: str, params: dict):
#     """The actual HTTP call + logging.
#
#     TODO:
#       t0 = time.perf_counter()
#       r = requests.get(BASE_URL + path, headers=HEADERS, params=params, timeout=20)
#       log to api_calls: path, r.status_code, elapsed ms,
#           credits from r.json()["status"]["credit_count"]
#       handle 429 (rate limited) with a backoff + retry — see the rate limit docs
#       r.raise_for_status(); return r.json()["data"]
#
#     CMC wraps everything in {"status": {...}, "data": {...}}. Read status.error_message
#     on failure — it's far more useful than the HTTP code alone.
#     """
#     ...


# ---------------------------------------------------------------------------
# Endpoints. Verify each path in the docs before you rely on it.
# ---------------------------------------------------------------------------

# def listings(limit=500, sort="volume_24h"):
#     """/v1/cryptocurrency/listings/latest — your universe.
#     NOTE: limit=5000 is not one credit. Check the credit rules before you widen it."""
#     ...


# def market_pairs(token_id: int, limit=100):
#     """/v1/cryptocurrency/market-pairs/latest — THE CORE ENDPOINT.
#
#     One call per token. At 500 tokens that's ~500 calls per full refresh.
#     Returns every venue the token trades on. You want, per pair:
#         exchange name, pair name, quote volume 24h, price
#
#     These become rows in `pairs`, and `pairs` is what the impact model is built on.
#     If this returns thin data, run scripts/day1_validate.py and rethink."""
#     ...


# def quotes(ids: list[int]):
#     """/v2/cryptocurrency/quotes/latest — BATCH these. ids=1,2,3 in one call."""
#     ...


# def ohlcv_historical(token_id: int, days=90):
#     """/v2/cryptocurrency/ohlcv/historical — volatility (sigma) + Hindsight.
#     TIER-GATED. Check your depth on day one; if it's shallow, Hindsight shrinks."""
#     ...


# def dex_spot_pairs(**kw):
#     """/v4/dex/spot-pairs/latest — on-chain pools. Under-used by everyone else,
#     which is exactly why it scores on 'interesting use of the API'."""
#     ...
