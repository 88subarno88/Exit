"""Fit the impact curve against real order books, then generalise to tokens that have none.

Run:  python -m ingest.calibrate          # after at least one ingest.books snapshot

The curve (impact.py) is   bps = 10_000 * Y * sigma * (Q / V) ** delta
The textbook square-root law fixes delta = 0.5. Our ground truth is an IMMEDIATE
sale, which the square-root law was never meant to describe (it is for orders
worked over a day while the book refills) -- so we fit delta too, and let the
data say what it is.

GROUND TRUTH, per (token, day):
  the latest snapshot from every venue that day, bids MERGED into one book --
  an exit routed across Binance/OKX/Coinbase/Kraken at once -- walked for each
  size, measured against the consolidated mid (so the half-spread is included).
  Inputs are the PREVIOUS day's CMC volume and 30 days of closes before it:
  nothing the model sees postdates the snapshot.

THREE MODELS, compared out-of-sample with GroupKFold by TOKEN:
  1. sqrt      one global Y, delta fixed at 0.5        (the textbook baseline)
  2. power     one global Y, fitted delta              (option a)
  3. learned   global delta, Y per token predicted by gradient boosting from
               features every CMC token has -- so it applies to tokens with NO
               public order book. That is the whole justification for ML here:
               train on what we can measure, generalise to what we cannot.
Whichever wins out-of-sample is written to ingest/calibration.json and used by
impact.py. If the learned model doesn't beat the power law, we ship the power law.

Learn:
  https://scikit-learn.org/stable/modules/ensemble.html
  https://scikit-learn.org/stable/modules/cross_validation.html#group-k-fold
"""
import os, json, math, zlib, sqlite3, datetime as dt
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import HuberRegressor
from sklearn.model_selection import GroupKFold

from .config import DB_PATH
from .books import fill_price
from .impact import sigma_daily

HERE = os.path.dirname(__file__)
CALIBRATION_PATH = os.path.join(HERE, "calibration.json")
MODEL_PATH = os.path.join(HERE, "y_model.joblib")
REPORT_PATH = os.path.join(HERE, "..", "data", "calibration_report.md")

SIZES = (10_000, 100_000, 1_000_000, 10_000_000)   # $1k is pure half-spread; not an impact
SIGMA_WINDOW = 30
N_FOLDS = 5
LEARNED_MARGIN = 0.05       # learned must cut median error by 5% to replace power law
FEATURES = ["log_sigma", "log_volume", "log_mcap", "turnover", "history_days"]


# ---------------------------------------------------------------------------
# Ground truth
# ---------------------------------------------------------------------------

def _consolidated_books(db):
    """{(token_id, day): {"bids": [...], "asks": [...], "venues": n}} from book_raw,
    using each venue's latest snapshot per day."""
    latest = db.execute("""
        SELECT token_id, venue, substr(ts, 1, 10) AS day, MAX(ts)
        FROM book_raw GROUP BY token_id, venue, day""").fetchall()
    out = {}
    for tid, venue, day, ts in latest:
        blob, truncated = db.execute("SELECT levels_zlib, truncated FROM book_raw "
                                     "WHERE token_id=? AND venue=? AND ts=?",
                                     (tid, venue, ts)).fetchone()
        lv = json.loads(zlib.decompress(blob))
        b = out.setdefault((tid, day), {"bids": [], "asks": [], "venues": 0, "truncated": False})
        b["bids"] += lv["bids"]
        b["asks"] += lv["asks"]
        b["venues"] += 1
        b["truncated"] |= bool(truncated)
    for b in out.values():
        b["bids"].sort(key=lambda x: -x[0])
        b["asks"].sort(key=lambda x: x[0])
    return out


def _cmc_inputs(db, tid, day):
    """Volume, mcap and sigma from daily candles strictly BEFORE `day`."""
    rows = db.execute("""
        SELECT time_open, close, volume, market_cap FROM ohlcv
        WHERE token_id=? AND interval='d' AND time_open < ?
        ORDER BY time_open DESC LIMIT ?""", (tid, day, SIGMA_WINDOW + 1)).fetchall()[::-1]
    if not rows:
        return None
    first = db.execute("SELECT MIN(time_open) FROM ohlcv WHERE token_id=? AND interval='d'",
                       (tid,)).fetchone()[0]
    _, _, vol, mcap = rows[-1]
    history = (dt.date.fromisoformat(day) - dt.date.fromisoformat(first[:10])).days
    return {"volume": vol, "mcap": mcap, "sigma": sigma_daily([r[1] for r in rows]),
            "history_days": history}


def load_samples(db_path=DB_PATH):
    """One row per (token, day, size) with the observed exit cost and CMC inputs.
    Returns (rows, censored, stats).

    `censored`: sales the merged book could NOT absorb at all. They can't be fitted
    (there is no cost to fit), but they are the most important outcome for an exit
    tool, so they're scored: a model that prices them cheaply is giving false
    comfort. If any venue capped its levels we can't tell thin from truncated, so
    those are dropped and counted instead."""
    db = sqlite3.connect(db_path)
    rows, censored, dropped_fill, dropped_inputs = [], [], 0, 0
    for (tid, day), b in _consolidated_books(db).items():
        if not b["bids"] or not b["asks"]:
            continue
        mid = (b["bids"][0][0] + b["asks"][0][0]) / 2
        inp = _cmc_inputs(db, tid, day)
        if not inp or not inp["volume"] or not inp["sigma"] or not inp["mcap"]:
            dropped_inputs += 1
            continue
        for size in SIZES:
            avg = fill_price(b["bids"], size)
            if avg is None:
                if b["truncated"]:
                    dropped_fill += 1
                else:
                    censored.append({"token_id": tid, "day": day, "size": size, "bps": None,
                                     "venues": b["venues"], **inp})
                continue
            bps = 10_000 * (mid - avg) / mid
            if bps <= 0:            # crossed venues can make a tiny sale "profitable"
                continue
            rows.append({"token_id": tid, "day": day, "size": size, "bps": bps,
                         "venues": b["venues"], **inp})
    return rows, censored, {"dropped_truncated": dropped_fill,
                            "dropped_no_cmc_inputs": dropped_inputs}


# ---------------------------------------------------------------------------
# Models. All work in log space: y = log(bps / (10_000 * sigma)) = log Y + delta * x
# ---------------------------------------------------------------------------

def _arrays(rows):
    x = np.array([math.log(r["size"] / r["volume"]) for r in rows])
    y = np.array([math.log(r["bps"] / (10_000 * r["sigma"])) if r["bps"] else np.nan
                  for r in rows])
    F = np.array([[math.log(r["sigma"]), math.log(r["volume"]), math.log(r["mcap"]),
                   r["volume"] / r["mcap"], r["history_days"]] for r in rows])
    g = np.array([r["token_id"] for r in rows])
    return x, y, F, g


def implied_Y(true_bps, size_usd, volume_24h, sigma_daily, delta=0.5):
    """The Y that WOULD have produced the observed cost under exponent `delta`."""
    return true_bps / (10_000 * sigma_daily * (size_usd / volume_24h) ** delta)


def fit_sqrt(x, y):
    """Baseline: delta = 0.5, Y = median implied Y (median -- outliers will eat a mean)."""
    return {"logY": float(np.median(y - 0.5 * x)), "delta": 0.5}


def fit_power(x, y):
    """Global Y and delta. Huber loss: a handful of broken books can't drag the slope."""
    h = HuberRegressor().fit(x.reshape(-1, 1), y)
    return {"logY": float(h.intercept_), "delta": float(h.coef_[0])}


def fit_learned(x, y, F):
    """Global delta from the power law, then log Y per ROW is the residual; a GBM
    learns it from token features only (nothing from the book), so it can price
    tokens that have no book at all."""
    p = fit_power(x, y)
    gbm = GradientBoostingRegressor(n_estimators=200, max_depth=2, learning_rate=0.05,
                                    subsample=0.8, loss="huber", random_state=0)
    gbm.fit(F, y - p["delta"] * x)
    return {"delta": p["delta"], "gbm": gbm}


def _predict(name, m, x, F):
    if name == "learned":
        return m["gbm"].predict(F) + m["delta"] * x
    return m["logY"] + m["delta"] * x


def _fit_all(x, y, F):
    return {"sqrt": fit_sqrt(x, y), "power": fit_power(x, y), "learned": fit_learned(x, y, F)}


def cross_validate(rows, censored):
    """Out-of-fold predictions for every model, split by TOKEN.

    Ten rows from one token are not ten independent observations; a random split
    leaks the token into train and test and the score means nothing. Censored rows
    are predicted by the fold that held their token out; tokens with no fillable
    rows at all were never in training, so the full-data model predicts them."""
    x, y, F, g = _arrays(rows)
    cx, _, cF, cg = _arrays(censored) if censored else (np.array([]),) * 4
    n_folds = min(N_FOLDS, len(set(g)))
    names = ("sqrt", "power", "learned")
    oof = {k: np.zeros_like(y) for k in names}
    c_oof = {k: np.full(len(censored), np.nan) for k in names}
    for tr, te in GroupKFold(n_splits=n_folds).split(x, y, groups=g):
        models = _fit_all(x[tr], y[tr], F[tr])
        held_out = np.isin(cg, g[te]) if len(censored) else np.array([], bool)
        for k, m in models.items():
            oof[k][te] = _predict(k, m, x[te], F[te])
            if held_out.any():
                c_oof[k][held_out] = _predict(k, m, cx[held_out], cF[held_out])
    if len(censored):
        rest = np.isnan(c_oof["sqrt"])
        if rest.any():
            for k, m in _fit_all(x, y, F).items():
                c_oof[k][rest] = _predict(k, m, cx[rest], cF[rest])
    return y, oof, c_oof, n_folds


FALSE_COMFORT_BPS = 1_000     # predicting < 10% for a sale no book could absorb


def _false_comfort(censored, pred):
    if not len(censored):
        return None
    sig = np.array([r["sigma"] for r in censored])
    return float(np.mean(10_000 * sig * np.exp(pred) < FALSE_COMFORT_BPS))


def _metrics(rows, y, pred):
    """Median absolute error in bps, median ratio error, and R^2 on log cost."""
    obs = np.array([r["bps"] for r in rows])
    sig = np.array([r["sigma"] for r in rows])
    p_bps = 10_000 * sig * np.exp(pred)
    r2 = 1 - np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2)
    return {"mdae_bps": float(np.median(np.abs(p_bps - obs))),
            "median_factor": float(np.exp(np.median(np.abs(pred - y)))),
            "r2_log": float(r2)}


# ---------------------------------------------------------------------------
# Report + ship
# ---------------------------------------------------------------------------

def report(rows, censored, stats):
    y, oof, c_oof, n_folds = cross_validate(rows, censored)
    x, _, F, g = _arrays(rows)
    overall = {k: {**_metrics(rows, y, v), "false_comfort": _false_comfort(censored, c_oof[k])}
               for k, v in oof.items()}
    by_size = {}
    for s in SIZES:
        idx = [i for i, r in enumerate(rows) if r["size"] == s]
        if idx:
            sub = [rows[i] for i in idx]
            by_size[s] = {k: _metrics(sub, y[idx], v[idx]) for k, v in oof.items()}

    full = _fit_all(x, y, F)
    winner = "power"
    if overall["learned"]["mdae_bps"] < (1 - LEARNED_MARGIN) * overall["power"]["mdae_bps"]:
        winner = "learned"
    if overall["sqrt"]["mdae_bps"] < overall[winner]["mdae_bps"]:
        winner = "sqrt"

    days = sorted({r["day"] for r in rows})
    L = []
    L.append(f"# Calibration report ({dt.date.today()})\n")
    L.append(f"{len(rows)} rows, {len(set(g))} tokens, {len(days)} day(s) "
             f"({days[0]} to {days[-1]}). Target: cost of selling immediately across "
             f"all measured venues, vs consolidated mid. {n_folds}-fold CV grouped by token.")
    L.append(f"{len(censored)} more sales could not be absorbed by the merged book at all "
             f"(no venue truncated). They can't be fitted, so they're scored instead: "
             f"'false comfort' = share a model prices under {FALSE_COMFORT_BPS // 100}%. "
             f"Dropped: {stats['dropped_truncated']} sales where a venue capped its levels "
             f"(thin vs truncated unknowable); {stats['dropped_no_cmc_inputs']} token-days "
             f"with no CMC volume/sigma.\n")
    L.append("| model | Y | delta | median abs err | median factor off | R^2 (log) | false comfort |")
    L.append("|---|---|---|---|---|---|---|")
    for k, label in (("sqrt", "textbook sqrt, global Y"), ("power", "power law, global Y"),
                     ("learned", "learned Y per token")):
        m, f = overall[k], full[k]
        Y = f"{math.exp(f['logY']):.3g}" if "logY" in f else "per token"
        fc = "-" if m["false_comfort"] is None else f"{m['false_comfort']:.0%}"
        L.append(f"| {label}{' **(shipped)**' if k == winner else ''} | {Y} | "
                 f"{f['delta']:.3f} | {m['mdae_bps']:.1f} bps | x{m['median_factor']:.2f} | "
                 f"{m['r2_log']:.3f} | {fc} |")
    L.append("\nMedian absolute error by order size (out-of-fold, bps):\n")
    L.append("| size | n | sqrt | power | learned |")
    L.append("|---|---|---|---|---|")
    for s, m in by_size.items():
        n = sum(1 for r in rows if r["size"] == s)
        L.append(f"| ${s:,} | {n} | " + " | ".join(f"{m[k]['mdae_bps']:.1f}"
                 for k in ("sqrt", "power", "learned")) + " |")
    imp = sorted(zip(FEATURES, full["learned"]["gbm"].feature_importances_), key=lambda t: -t[1])
    L.append("\nWhat predicts a token's Y (GBM feature importance): " +
             ", ".join(f"{n} {v:.2f}" for n, v in imp))
    if winner != "learned":
        L.append("\nThe learned model did not beat the power law by the required "
                 f"{LEARNED_MARGIN:.0%}, so the power law ships. Published as a negative result.")
    text = "\n".join(L)

    cal = {"model": winner, "delta": full[winner]["delta"],
           "Y": math.exp(full[winner]["logY"]) if "logY" in full[winner]
           else math.exp(full["power"]["logY"]),
           "target": "immediate sale across binance/okx/coinbase/kraken vs consolidated mid",
           "fitted_on": {"rows": len(rows), "censored": len(censored),
                         "tokens": len(set(g)), "days": days},
           "cv": overall, "features": FEATURES, "date": dt.date.today().isoformat()}
    return text, cal, full


def main():
    rows, censored, stats = load_samples()
    if len({r["token_id"] for r in rows}) < 10:
        raise SystemExit(f"Only {len(rows)} usable rows -- run `python -m ingest.books` first.")
    text, cal, full = report(rows, censored, stats)
    print(text)
    with open(CALIBRATION_PATH, "w") as f:
        json.dump(cal, f, indent=1)
    if cal["model"] == "learned":
        import joblib
        joblib.dump(full["learned"]["gbm"], MODEL_PATH)
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        f.write(text + "\n")
    print(f"\nWrote {os.path.relpath(CALIBRATION_PATH)} (used by impact.py) and "
          f"{os.path.relpath(REPORT_PATH)} (for METHODOLOGY.md).")


if __name__ == "__main__":
    main()
