"""HINDSIGHT -- the model run backwards through past collapses.

Run once (needs the CMC plan to still serve 2022-23 history -- do it before 30 Sep):
    python -m ingest.hindsight            # fetch candles + compute
    python -m ingest.hindsight --compute  # recompute only, no API calls (after re-calibrating)

For each case: daily candles from 210 days before the collapse to 30 days after,
then for every day the SAME rating the live site uses -- previous day's volume,
30-day sigma, the calibrated curve. Nothing here is fitted to the collapse.

Honest limits, printed on the page:
  * volume and volatility are real CMC history; venue structure then is unknown
  * Y and delta were calibrated on 2026 order books and are assumed to hold in 2022
"""
import sys, json, sqlite3, argparse, datetime as dt
import requests

from .config import DB_PATH, BASE_URL, HEADERS
from .impact import sigma_daily, max_position, exit_cost, grade, Y_DEFAULT, DELTA
from . import cmc

CASES = [
    # key, CMC id, label, collapse date, one-line context
    ("luna", 4172, "LUNA (now LUNC)", "2022-05-09", "UST lost its peg and LUNA went to ~0 within days."),
    ("ftt", 4195, "FTT", "2022-11-08", "FTX halted withdrawals; FTT fell ~75% in two days."),
    ("crv", 6538, "CRV", "2023-07-30", "A Vyper compiler bug drained Curve pools; CRV's founder had large CRV-backed loans."),
]
BEFORE, AFTER, SIGMA_WINDOW = 210, 30, 30
PROBE_SIZE = 100_000


def fetch(db, case):
    key, tid, _, day, _ = case
    d0 = dt.date.fromisoformat(day)
    params = {"id": tid, "time_period": "daily", "interval": "daily", "convert": "USD",
              "time_start": (d0 - dt.timedelta(days=BEFORE + SIGMA_WINDOW + 1)).isoformat(),
              "time_end": (d0 + dt.timedelta(days=AFTER)).isoformat()}
    r = requests.get(BASE_URL + "/v2/cryptocurrency/ohlcv/historical", headers=HEADERS,
                     params=params, timeout=60)
    body = r.json()
    st = body.get("status", {})
    cmc._log("/v2/cryptocurrency/ohlcv/historical", r.status_code, 0, st.get("credit_count") or 0)
    if r.status_code != 200:
        sys.exit(f"{key}: {st.get('error_message')}")
    data = body["data"]
    data = data if "quotes" in data else next(iter(data.values()))
    data = data[0] if isinstance(data, list) else data
    rows = [(key, tid, q["time_open"][:10], q["quote"]["USD"]["close"],
             q["quote"]["USD"]["volume"], q["quote"]["USD"].get("market_cap"))
            for q in data["quotes"] if q["quote"]["USD"].get("close")]
    db.executemany("INSERT OR REPLACE INTO hindsight_candles(case_key, token_id, day, close, "
                   "volume, market_cap) VALUES (?,?,?,?,?,?)", rows)
    db.commit()
    print(f"  {key}: {len(rows)} daily candles, {st.get('credit_count')} credits")


def compute(db):
    """Rate every day of every case with the current calibration."""
    db.execute("DELETE FROM hindsight")
    for key, tid, _, _, _ in CASES:
        c = db.execute("SELECT day, close, volume, market_cap FROM hindsight_candles "
                       "WHERE case_key=? ORDER BY day", (key,)).fetchall()
        out = []
        for i in range(SIGMA_WINDOW + 1, len(c)):
            day = c[i][0]
            prev = c[i - 1]                                   # yesterday's volume, like live
            sig = sigma_daily([x[1] for x in c[i - SIGMA_WINDOW - 1:i]])
            mp = max_position(prev[2], sig)
            ec = exit_cost(PROBE_SIZE, prev[2], sig)
            out.append((key, day, c[i][1], prev[2], c[i][3], sig, mp, grade(mp),
                        ec["bps"] if ec else None))
        db.executemany("INSERT INTO hindsight(case_key, day, close, volume, market_cap, sigma, "
                       "max_position, grade, exit_100k_bps) VALUES (?,?,?,?,?,?,?,?,?)", out)
    db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('hindsight_calibration', ?)",
               (json.dumps({"Y": Y_DEFAULT, "delta": DELTA}),))
    # the web app reads case labels from the DB, so it never imports this module
    db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('hindsight_cases', ?)",
               (json.dumps([dict(zip(("key", "token_id", "label", "date", "context"), c))
                            for c in CASES]),))
    db.commit()


def summary(db):
    """Readings at fixed offsets before each collapse -- what the page headlines."""
    out = {}
    for key, _, label, day, context in CASES:
        d0 = dt.date.fromisoformat(day)
        pts = {}
        for off in (-90, -30, -7, 0, 7):
            d = (d0 + dt.timedelta(days=off)).isoformat()
            r = db.execute("SELECT day, close, max_position, grade, exit_100k_bps, sigma, volume "
                           "FROM hindsight WHERE case_key=? AND day<=? ORDER BY day DESC LIMIT 1",
                           (key, d)).fetchone()
            if r:
                pts[off] = dict(zip(("day", "close", "max_position", "grade", "exit_100k_bps",
                                     "sigma", "volume"), r))
        out[key] = {"label": label, "date": day, "context": context, "points": pts}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--compute", action="store_true", help="recompute only, no API calls")
    a = ap.parse_args()
    db = sqlite3.connect(DB_PATH)
    if not a.compute:
        for case in CASES:
            fetch(db, case)
    compute(db)
    for key, s in summary(db).items():
        print(f"\n{s['label']} (collapse {s['date']})")
        for off, p in s["points"].items():
            mp = p["max_position"]
            print(f"  T{off:+4d}d {p['day']}  price ${p['close']:>10.4g}  grade {p['grade']:<4} "
                  f"max pos ${mp or 0:>14,.0f}  $100k exit {p['exit_100k_bps'] or 0:6.0f} bps  "
                  f"sigma {p['sigma'] or 0:.3f}  vol ${p['volume'] / 1e6:,.0f}M")


if __name__ == "__main__":
    main()
