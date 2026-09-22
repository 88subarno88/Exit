#!/usr/bin/env python3
"""DAY ONE GO/NO-GO CHECK -- DEX edition.

The original check (scripts/day1_validate_market_pairs.py) got 403 on
/v1/cryptocurrency/market-pairs/latest: the hackathon plan doesn't include it.
This version asks the same question of the DEX v4 surface, which the plan does
include: per venue, do we get PRICE, VOLUME and LIQUIDITY for real tokens?

Run:  python scripts/day1_validate.py | tee data/day1_dex_output.txt

Things learned probing /v4/dex/spot-pairs/latest (2026-09-22) that shape this:
  * dex_slug (or dex_id) is REQUIRED; network_slug alone -> 400.
  * base_asset_*/quote_asset_* filters, liquidity_min/max, volume_24h_min/max
    and `limit` are silently ignored: every call returns 100 pools for that DEX.
  * scroll_id is just a base64 offset ("MTAw" = "100"), and the list is CAPPED
    AT 200 POOLS per DEX -- page 3 is always empty, hand-made offsets too.
  * `sort` does work, and different sorts reach different pools. So we scan
    each venue by volume AND by liquidity, dedupe, and match client-side.
    Long-tail pools outside both top-200s are unreachable via discovery; once
    you know a pool address, /v4/dex/pairs/quotes/latest quotes it directly.
  * Match on CMC ucid, never symbol. The top-liquidity list is full of spoofs
    (look-alike Unicode tickers, $190M "liquidity" on unknown tokens).
  * BSC only works as network_id=14; network_slug "bsc" -> 400.
  * /v4/dex/networks/list and /v4/dex/listings/* returned 500 at the time.
"""
import os, sys, json, time, datetime
import requests
from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("CMC_API_KEY")
BASE = os.getenv("CMC_BASE_URL", "https://pro-api.coinmarketcap.com")
if not KEY:
    sys.exit("No CMC_API_KEY. Copy .env.example to .env and add your key.")

H = {"X-CMC_PRO_API_KEY": KEY, "Accept": "application/json"}

# (label, params). Each page costs 1 credit.
VENUES = [
    ("eth/uniswap-v3",      {"network_slug": "ethereum", "dex_slug": "uniswap-v3"}),
    ("eth/uniswap-v2",      {"network_slug": "ethereum", "dex_slug": "uniswap-v2"}),
    ("eth/uniswap-v4",      {"network_slug": "ethereum", "dex_slug": "uniswap-v4"}),
    ("eth/sushiswap",       {"network_slug": "ethereum", "dex_slug": "sushiswap"}),
    ("arb/uniswap-v3",      {"network_slug": "arbitrum", "dex_slug": "uniswap-v3"}),
    ("arb/camelot-v3",      {"network_slug": "arbitrum", "dex_slug": "camelot-v3"}),
    ("base/aerodrome-cl",   {"network_slug": "base", "dex_slug": "aerodrome-slipstream"}),
    ("bsc/pancakeswap-v2",  {"network_id": "14", "dex_slug": "pancakeswap-v2"}),
    ("sol/raydium",         {"network_slug": "solana", "dex_slug": "raydium"}),
    ("sol/raydium-clmm",    {"network_slug": "solana", "dex_slug": "raydium-clmm"}),
    ("sol/orca",            {"network_slug": "solana", "dex_slug": "orca"}),
    ("sol/pumpswap",        {"network_slug": "solana", "dex_slug": "pumpswap"}),
    ("hyperevm/hyperswap",  {"network_slug": "hyperevm", "dex_slug": "hyperswap-v3"}),
    ("hyperevm/project-x",  {"network_slug": "hyperevm", "dex_slug": "project-x"}),
]
SORTS = ("volume_24h", "liquidity")
MAX_PAGES = 2           # the API returns nothing past 200 pools anyway

# Native coins only trade on-chain in wrapped form. Counted, but labelled.
WRAPPED = {
    1:     {3717: "WBTC", 32994: "cbBTC"},
    1027:  {2396: "WETH"},
    32196: {35881: "WHYPE"},
    5426:  {16116: "wSOL"},
}
PRICE_TOL = 0.05        # pool price must be within 5% of CMC's aggregate price
MIN_POOL_VOL = 1_000    # below this a pool is dead or fake; its "liquidity" means nothing

credits = 0


def get(path, params):
    global credits
    t0 = time.perf_counter()
    try:
        r = requests.get(BASE + path, headers=H, params=params, timeout=30)
        body = r.json()
    except Exception as e:
        print(f"  [ERR] {path} {e}")
        return None
    ms = (time.perf_counter() - t0) * 1000
    st = body.get("status", {})
    credits += st.get("credit_count") or 0
    if r.status_code != 200 or st.get("error_code") not in (0, "0", None):
        print(f"  [{r.status_code}] {path} {ms:.0f}ms  ERROR: {st.get('error_message')}")
        return None
    return body.get("data")


print("\n=== 1. Universe: same 10 tokens as the market-pairs check ===")
data = get("/v1/cryptocurrency/listings/latest",
           {"limit": 200, "sort": "market_cap", "convert": "USD"})
if not data:
    sys.exit("listings failed -- check the key and your plan.")
picks = [data[i] for i in (0, 1, 4, 9, 24, 49, 74, 99, 149, 199) if i < len(data)]

info = get("/v2/cryptocurrency/info", {"id": ",".join(str(t["id"]) for t in picks)}) or {}

tokens = {}
for t in picks:
    q = t["quote"]["USD"]
    contracts = {c["contract_address"].lower()
                 for c in (info.get(str(t["id"])) or {}).get("contract_address") or []}
    ucids = {str(t["id"]): t["symbol"]}
    ucids.update({str(k): v for k, v in WRAPPED.get(t["id"], {}).items()})
    tokens[t["id"]] = {"symbol": t["symbol"], "price": q["price"],
                       "vol": q["volume_24h"], "mcap": q["market_cap"],
                       "contracts": contracts, "ucids": ucids, "pools": []}
    kind = f"{len(contracts)} contracts" if contracts else "native only"
    print(f"  {t['symbol']:<7} id={t['id']:<6} mcap=${q['market_cap']:>17,.0f} "
          f"vol=${q['volume_24h']:>15,.0f}  {kind}")

ucid_to_token = {u: tid for tid, tk in tokens.items() for u in tk["ucids"]}

def scan(params):
    """Every pool reachable for one venue: top 200 under each sort, deduped."""
    pools, pages = {}, 0
    for sort in SORTS:
        scroll = None
        for _ in range(MAX_PAGES):
            p = dict(params, sort=sort, **({"scroll_id": scroll} if scroll else {}))
            rows = get("/v4/dex/spot-pairs/latest", p)
            if not rows:
                break
            pages += 1
            for x in rows:
                pools.setdefault(x.get("contract_address"), x)
            scroll = rows[-1].get("scroll_id")
            if not scroll or len(rows) < 100:
                break
            time.sleep(0.1)
    return list(pools.values()), pages


print(f"\n=== 2. Scan {len(VENUES)} DEX venues (top 200 by volume + top 200 by liquidity) ===")
for label, params in VENUES:
    rows, pages = scan(params)
    hits = 0
    for x in rows:
        for side, other in (("base", "quote"), ("quote", "base")):
            tid = ucid_to_token.get(str(x.get(f"{side}_asset_ucid")))
            if tid is None:
                continue
            q = (x.get("quote") or [{}])[0]
            # `price` is the BASE asset in USD; price_by_quote_asset is base in quote units
            price = q.get("price")
            if side == "quote" and price and q.get("price_by_quote_asset"):
                price = price / q["price_by_quote_asset"]
            addr = (x.get(f"{side}_asset_contract_address") or "").lower()
            tk = tokens[tid]
            as_sym = tk["ucids"][str(x[f"{side}_asset_ucid"])]
            # only checkable for the token itself; wrapped aliases aren't in its info
            contract_ok = (addr in tk["contracts"]) if tk["contracts"] and as_sym == tk["symbol"] else None
            tk["pools"].append({
                "venue": label, "pool": x.get("contract_address"), "name": x.get("name"),
                "as": as_sym,
                "vs": x.get(f"{other}_asset_symbol"),
                "price": price, "volume_24h": q.get("volume_24h") or 0,
                "liquidity": q.get("liquidity") or 0,
                "contract_ok": contract_ok,
            })
            hits += 1
    print(f"  {label:<20} pages={pages:<3} pools_seen={len(rows):<5} matched={hits}")

print("\n=== 3. Per-token detail (top 5 USABLE pools by liquidity) ===")
rows_out = []
for tid, tk in tokens.items():
    pools = tk["pools"]
    good = [p for p in pools if p["liquidity"] > 0 and p["volume_24h"] >= MIN_POOL_VOL
            and p["price"] and abs(p["price"] / tk["price"] - 1) <= PRICE_TOL]
    liq = sum(p["liquidity"] for p in good)
    vol = sum(p["volume_24h"] for p in good)
    # Herfindahl index of liquidity across pools: 1.0 = everything in one pool
    hhi = sum((p["liquidity"] / liq) ** 2 for p in good) if liq else None
    wrapped_only = bool(good) and all(p["as"] != tk["symbol"] for p in good)
    rows_out.append((tk["symbol"], len(pools), len(good), liq, vol / tk["vol"] if tk["vol"] else 0,
                     hhi, len({p["venue"] for p in good}), wrapped_only))

    print(f"\n-- {tk['symbol']}  CMC price ${tk['price']:,.6g}  "
          f"({len(pools) - len(good)} of {len(pools)} pools rejected: dead, off-price or spoof)")
    if not good:
        print("   no usable pools on scanned venues")
    for p in sorted(good, key=lambda p: -p["liquidity"])[:5]:
        dev = (p["price"] / tk["price"] - 1) * 100 if p["price"] else float("nan")
        flag = "" if p["contract_ok"] in (True, None) else "  [contract not in CMC info]"
        print(f"   {p['venue']:<20} {p['as']:>6}/{p['vs']:<8} liq=${p['liquidity']:>14,.0f} "
              f"vol=${p['volume_24h']:>13,.0f} px_dev={dev:+6.2f}%{flag}")

print("\n" + "=" * 86)
print("VERDICT")
print("=" * 86)
print(f"{'symbol':<8}{'pools':>7}{'usable':>8}{'pool TVL*':>18}{'DEX/CMC vol':>13}"
      f"{'liq HHI':>9}{'venues':>8}  note")
for s, n, g, liq, share, hhi, nv, wr in rows_out:
    hhi_s = f"{hhi:.2f}" if hhi is not None else "-"
    print(f"{s:<8}{n:>7}{g:>8}{liq:>18,.0f}{share:>12.1%}{hhi_s:>9}{nv:>8}  "
          f"{'wrapped only' if wr else ''}")

ok = sum(1 for r in rows_out if r[2] >= 1)
multi = sum(1 for r in rows_out if r[6] >= 2)
print("* total TVL of pools containing the token (both sides) -- an upper bound, not depth.")
print(f"\n{ok}/{len(rows_out)} tokens have >=1 usable pool (liq>0, vol>=${MIN_POOL_VOL:,}, price within "
      f"{PRICE_TOL:.0%} of CMC); {multi} have usable pools on 2+ venues.")
print(f"Credits used this run: {credits}")
print("\n  >=7  -> GO. DEX pools are the per-venue layer; CEX order books (step 4) fill the rest.")
print("  4-6  -> GO, but CEX order books carry the model; DEX is a coverage bonus. Say so.")
print("  <4   -> STOP. Per-venue data isn't there on this plan; rethink the project.")
print("Tokens with no pools are usually native L1s with no wrapped form -- expected, and")
print("exactly what the public order books in step 4 are for.")

os.makedirs("data", exist_ok=True)
out = f"data/day1_dex_pools_{datetime.date.today()}.json"
with open(out, "w") as f:
    json.dump({tk["symbol"]: {k: (sorted(v) if isinstance(v, set) else v)
                              for k, v in tk.items()} for tk in tokens.values()},
              f, indent=1)
print(f"\nRaw matched pools saved to {out}")
