#!/usr/bin/env python3
"""DAY ONE GO/NO-GO CHECK.

Written complete on purpose -- it is a throwaway diagnostic, not part of the
product, and you need the answer before you build anything.

Run:  python scripts/day1_validate.py

What you are looking for, per token:
  * a non-trivial number of market pairs
  * per-pair VOLUME and PRICE actually populated

If those are there  -> build Exit.
If they are missing -> stop and rethink before writing the rest.
"""
import os, sys, json, time
import requests
from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("CMC_API_KEY")
BASE = os.getenv("CMC_BASE_URL", "https://pro-api.coinmarketcap.com")
if not KEY:
    sys.exit("No CMC_API_KEY. Copy .env.example to .env and add your key.")

H = {"X-CMC_PRO_API_KEY": KEY, "Accept": "application/json"}


def get(path, params):
    t0 = time.perf_counter()
    r = requests.get(BASE + path, headers=H, params=params, timeout=30)
    ms = (time.perf_counter() - t0) * 1000
    try:
        body = r.json()
    except Exception:
        sys.exit(f"Non-JSON response {r.status_code}: {r.text[:300]}")
    st = body.get("status", {})
    print(f"  [{r.status_code}] {path} {ms:.0f}ms credits={st.get('credit_count')}")
    if r.status_code != 200 or st.get("error_code"):
        print(f"  ERROR: {st.get('error_message')}")
        return None
    return body.get("data")


print("\n=== 1. Universe: 10 tokens across the cap spectrum ===")
data = get("/v1/cryptocurrency/listings/latest",
           {"limit": 200, "sort": "market_cap", "convert": "USD"})
if not data:
    sys.exit("listings failed -- check the key and your plan.")

# spread the sample: mega-cap through long tail
picks = [data[i] for i in (0, 1, 4, 9, 24, 49, 74, 99, 149, 199) if i < len(data)]
for t in picks:
    q = t["quote"]["USD"]
    print(f"  {t['symbol']:<8} id={t['id']:<7} mcap=${q['market_cap']:>16,.0f} "
          f"vol=${q['volume_24h']:>14,.0f}")

print("\n=== 2. THE CRITICAL CHECK: market-pairs per token ===")
verdict = []
for t in picks:
    print(f"\n-- {t['symbol']} (id {t['id']})")
    d = get("/v1/cryptocurrency/market-pairs/latest",
            {"id": t["id"], "limit": 100, "convert": "USD"})
    if not d:
        verdict.append((t["symbol"], 0, 0, 0)); continue

    pairs = d.get("market_pairs", [])
    with_vol = with_price = 0
    for p in pairs:
        q = (p.get("quote") or {}).get("USD") or {}
        if (q.get("volume_24h") or 0) > 0: with_vol += 1
        if (q.get("price") or 0) > 0:      with_price += 1

    print(f"   pairs={len(pairs)}  with_volume={with_vol}  with_price={with_price}")
    if pairs:
        p0 = pairs[0]
        print("   sample pair keys:", sorted(p0.keys()))
        print("   sample:", json.dumps(p0, indent=2)[:700])
    verdict.append((t["symbol"], len(pairs), with_vol, with_price))
    time.sleep(0.5)          # be polite; avoid tripping the rate limiter

print("\n" + "=" * 62)
print("VERDICT")
print("=" * 62)
print(f"{'symbol':<10}{'pairs':>8}{'w/ volume':>12}{'w/ price':>10}")
for s, n, v, p in verdict:
    print(f"{s:<10}{n:>8}{v:>12}{p:>10}")

ok = sum(1 for _, n, v, p in verdict if n >= 3 and v >= 3 and p >= 3)
print(f"\n{ok}/{len(verdict)} tokens returned usable per-venue data.")
print("\n  >=8  -> GO. Build Exit.")
print("  4-7  -> GO, but cap the universe at large/mid caps and say so in the README.")
print("  <4   -> STOP. Re-read the docs, check your tier, then reconsider the project.")
print("\nAlso save this output -- it is your 'visible evidence of a real API call'.")
