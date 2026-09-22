#!/usr/bin/env python3
"""Grade distribution across the whole universe, with the current calibration.

Run:  python scripts/grades.py

Check before publishing any grade: if 90% of tokens land in one bucket, the
thresholds in impact.GRADE_SCALE are wrong, not the market.
"""
import os, sys, sqlite3, collections
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ingest.config import DB_PATH
from ingest.impact import sigma_daily, rate, GRADE_SCALE, Y_DEFAULT, DELTA

db = sqlite3.connect(DB_PATH)
counts, examples, extrapolated, unrated = collections.Counter(), {}, 0, 0
for tid, sym in db.execute("SELECT id, symbol FROM tokens"):
    rows = db.execute("SELECT close, volume, market_cap FROM ohlcv WHERE token_id=? AND interval='d' "
                      "ORDER BY time_open DESC LIMIT 31", (tid,)).fetchall()[::-1]
    if not rows:
        unrated += 1
        continue
    r = rate(rows[-1][1], sigma_daily([x[0] for x in rows]))
    counts[r["grade"]] += 1
    extrapolated += r["max_position_extrapolated"]
    examples.setdefault(r["grade"], []).append((rows[-1][2] or 0, sym))

total = sum(counts.values())
print(f"Calibration: Y={Y_DEFAULT:.2f} delta={DELTA:.3f}   {total} tokens rated, {unrated} without candles\n")
print(f"{'grade':<6}{'max position >=':>16}{'tokens':>8}  {'share':>6}  largest by mcap")
for g, floor in GRADE_SCALE + [("NR", None)]:
    n = counts.get(g, 0)
    ex = ", ".join(s for _, s in sorted(examples.get(g, []), reverse=True)[:5])
    fl = f"${floor:,}" if floor is not None else "no data"
    print(f"{g:<6}{fl:>16}{n:>8}  {n / total:>6.0%}  {ex}" if total else g)
print(f"\n{extrapolated} tokens have a max position above the $10M calibration limit "
      f"(show them as '> $10M').")
top = max(counts.values()) / total if total else 0
if top > 0.5:
    print(f"WARNING: {top:.0%} of tokens share one grade -- the thresholds need spreading out.")
