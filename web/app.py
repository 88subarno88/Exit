"""The six surfaces. Flask: https://flask.palletsprojects.com/en/3.0.x/quickstart/

RULE: this file NEVER calls CoinMarketCap. It only reads SQLite.
If you break that rule, your demo dies when the tier expires on 30 Sep.

It also never imports ingest.config (that needs a CMC key; the deployed site has
none). The only ingest module it touches is impact.py -- pure maths plus
calibration.json -- so the token page draws the exact curve the ratings used.

Run:  python -m web.app              # http://127.0.0.1:5000
      SITE_DB=path/to.db python -m web.app

Charts: https://www.chartjs.org/docs/latest/
"""
import os, json, time, sqlite3, datetime as dt
from collections import defaultdict, deque
from flask import Flask, render_template, jsonify, request, redirect, url_for, abort, g

from ingest import impact

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Local: the working DB. Deployed: SITE_DB=web/site.db (scripts/export_site.py).
DB = os.getenv("SITE_DB") or os.path.join(ROOT, os.getenv("DB_PATH", "data/exit.db"))
if not os.path.isabs(DB):
    DB = os.path.join(ROOT, DB)
STALE_HOURS = 36
GRADES = [name for name, _ in impact.GRADE_SCALE] + ["NR"]

app = Flask(__name__)


# ---------------------------------------------------------------------------
# data access -- read-only, one connection per request
# ---------------------------------------------------------------------------

def db():
    if "db" not in g:
        g.db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def _close(_):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def q(sql, *args):
    return db().execute(sql, args).fetchall()


def q1(sql, *args):
    return db().execute(sql, args).fetchone()


def latest_ts():
    r = q1("SELECT MAX(ts) AS ts FROM ratings")
    return r["ts"] if r else None


def latest_ratings():
    return q("SELECT * FROM ratings WHERE ts = ? ORDER BY market_cap DESC", latest_ts())


def meta(key, default=None):
    r = q1("SELECT value FROM meta WHERE key = ?", key)
    return json.loads(r["value"]) if r else default


@app.context_processor
def _globals():
    """The 'last updated' stamp on every page, and whether it's stale."""
    ts = latest_ts()
    stale = False
    if ts:
        age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(ts)
        stale = age.total_seconds() > STALE_HOURS * 3600
    return {"as_of": ts, "stale": stale, "grades": GRADES, "cal": impact.CALIBRATION or {}}


# ---------------------------------------------------------------------------
# formatting, shared by every template
# ---------------------------------------------------------------------------

@app.template_filter("usd")
def usd(v, digits=3):
    if v is None:
        return "—"
    a = abs(v)
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "k")):
        if a >= div:
            return f"${v / div:.{digits}g}{suf}"
    return f"${v:,.0f}" if a >= 1 else f"${v:.4g}"


@app.template_filter("bps")
def bps(v):
    if v is None:
        return "—"
    return f"{v / 100:.1f}%" if v >= 100 else f"{v:.0f} bps" if v >= 1 else f"{v:.1f} bps"


@app.template_filter("price")
def price(v):
    return "—" if v is None else f"${v:,.2f}" if v >= 1 else f"${v:.4g}"


@app.template_filter("todate")
def todate(v):
    return dt.date.fromisoformat(v[:10])


@app.template_filter("maxpos")
def maxpos(r):
    """Above the calibrated range, never print the extrapolated number."""
    if r["max_position"] is None:
        return "not rated"
    if r["extrapolated"]:
        return "> " + usd(impact.CALIBRATED_MAX_USD)
    return usd(r["max_position"])


# ---------------------------------------------------------------------------
# pages
# ---------------------------------------------------------------------------

@app.route("/")
def map_view():
    """SURFACE 1 -- THE MAP. Every token: market cap vs what can actually leave."""
    rows = latest_ratings()
    if not rows:
        return render_template("empty.html"), 503
    rated = [r for r in rows if r["exit_100k_bps"] is not None]
    over5 = sum(1 for r in rated if r["exit_100k_bps"] > 500)
    over2 = sum(1 for r in rated if r["exit_100k_bps"] > 200)
    points = [{"s": r["symbol"], "slug": r["slug"], "g": r["grade"],
               "x": r["market_cap"], "y": min(r["max_position"], impact.CALIBRATED_MAX_USD),
               "ext": bool(r["extrapolated"])}
              for r in rows if r["max_position"] and r["market_cap"]]
    counts = {gr: sum(1 for r in rows if r["grade"] == gr) for gr in GRADES}
    return render_template("map.html", n=len(rows), rated=len(rated), over5=over5,
                           over2=over2, points=points, counts=counts)


@app.route("/search")
def search():
    term = (request.args.get("q") or "").strip()
    if not term:
        return redirect(url_for("map_view"))
    hits = q("SELECT slug, symbol, name, grade, market_cap FROM ratings WHERE ts = ? AND "
             "(UPPER(symbol) = UPPER(?) OR slug = LOWER(?) OR name LIKE ?) "
             "ORDER BY market_cap DESC LIMIT 20", latest_ts(), term, term, f"%{term}%")
    exact = [h for h in hits if h["symbol"].upper() == term.upper() or h["slug"] == term.lower()]
    if len(exact) == 1:
        return redirect(url_for("token", slug=exact[0]["slug"]))
    return render_template("search.html", term=term, hits=hits)


@app.route("/token/<slug>")
def token(slug):
    """SURFACE 2 -- the product: headline -> evidence -> caveat -> methodology."""
    r = q1("SELECT * FROM ratings WHERE slug = ? ORDER BY ts DESC LIMIT 1", slug)
    if r is None:
        abort(404)
    curve = impact.cost_curve(r["volume_24h"], r["sigma"], r["Y"], delta=r["delta"])
    band = [(s, *(impact.band_bps(b) or (None, None))) for s, b, _ in curve]
    observed = q("SELECT size_usd, bps, status, venues FROM observed_costs WHERE token_id = ? "
                 "AND day = (SELECT MAX(day) FROM observed_costs WHERE token_id = ?) "
                 "ORDER BY size_usd", r["token_id"], r["token_id"])
    venues = q("""SELECT venue, pair, spread_bps, depth_2pct_usd, status, impact_mid_bps, levels
                  FROM books WHERE token_id = ? AND side = 'sell' AND size_usd = 100000
                  AND ts = (SELECT MAX(ts) FROM books WHERE token_id = ?)
                  ORDER BY depth_2pct_usd DESC""", r["token_id"], r["token_id"])
    history = q("SELECT ts, grade, max_position FROM ratings WHERE token_id = ? ORDER BY ts",
                r["token_id"])
    exits = []
    for s in (10_000, 100_000, 1_000_000, 10_000_000):
        e = impact.exit_cost(s, r["volume_24h"], r["sigma"], r["Y"], r["delta"])
        exits.append((s, e, impact.band_bps(e["bps"]) if e else None))
    return render_template("token.html", r=r, curve=curve, band=band, observed=observed,
                           venues=venues, history=history, exits=exits,
                           calibrated_max=impact.CALIBRATED_MAX_USD,
                           scale=impact.GRADE_SCALE, tol=impact.TOLERANCE_BPS)


@app.route("/ratings")
def ratings():
    """SURFACE 3 -- league table, liquidity rank, downgrade feed."""
    tab = request.args.get("tab", "grades")
    rows = latest_ratings()
    by_cap = {r["token_id"]: i + 1 for i, r in enumerate(rows)}
    liquid = sorted([r for r in rows if r["max_position"]], key=lambda r: -r["max_position"])
    liquidity = [(i + 1, by_cap[r["token_id"]] - (i + 1), r) for i, r in enumerate(liquid)]
    feed = q("""SELECT r.ts, r.symbol, r.slug, p.grade AS old, r.grade AS new, r.max_position
                FROM ratings r JOIN ratings p ON p.token_id = r.token_id
                 AND p.ts = (SELECT MAX(ts) FROM ratings WHERE token_id = r.token_id AND ts < r.ts)
                WHERE p.grade != r.grade ORDER BY r.ts DESC, r.market_cap DESC LIMIT 100""")
    runs = q("SELECT ts, COUNT(*) AS n FROM ratings GROUP BY ts ORDER BY ts DESC LIMIT 10")
    counts = {gr: sum(1 for r in rows if r["grade"] == gr) for gr in GRADES}
    invest = sum(counts[g] for g in ("AAA", "AA", "A", "BBB"))   # clears $300k at 2%
    summary = {"total": len(rows), "investment": invest, "nr": counts["NR"],
               "speculative": len(rows) - invest - counts["NR"]}
    return render_template("ratings.html", tab=tab, rows=rows, liquidity=liquidity,
                           feed=feed, runs=runs, counts=counts, summary=summary)


@app.route("/hindsight")
def hindsight():
    """SURFACE 4 -- the model run backwards. States what it saw AND what it didn't."""
    cases = meta("hindsight_cases", [])
    out = []
    for c in cases:
        series = q("SELECT day, close, max_position, grade, exit_100k_bps FROM hindsight "
                   "WHERE case_key = ? ORDER BY day", c["key"])
        d0 = dt.date.fromisoformat(c["date"])
        pts = []
        for off in (-90, -30, -7, 0, 7, 30):
            d = (d0 + dt.timedelta(days=off)).isoformat()
            p = q1("SELECT day, close, max_position, grade, exit_100k_bps FROM hindsight "
                   "WHERE case_key = ? AND day <= ? ORDER BY day DESC LIMIT 1", c["key"], d)
            if p:
                pts.append((off, dict(p)))
        # did the grade fall below investment grade (BBB) before the collapse?
        warned = q1("SELECT MIN(day) AS day FROM hindsight WHERE case_key = ? AND day < ? "
                    "AND day >= ? AND grade IN ('BB','B','CCC','D')", c["key"], c["date"],
                    (d0 - dt.timedelta(days=90)).isoformat())
        out.append({**c, "series": [dict(s) for s in series], "points": pts,
                    "warned": warned["day"] if warned else None})
    return render_template("hindsight.html", cases=out,
                           hcal=meta("hindsight_calibration", {}))


@app.route("/methodology")
def methodology():
    """SURFACE 5 -- the model, calibration, baseline table, limits."""
    return render_template("methodology.html", scale=impact.GRADE_SCALE,
                           tol=impact.TOLERANCE_BPS, calibrated_max=impact.CALIBRATED_MAX_USD,
                           hi=impact.CONCENTRATION_HHI)


@app.route("/debug")
def debug():
    """SURFACE 6 -- live evidence of real API calls, and data freshness."""
    calls = q("SELECT * FROM api_calls ORDER BY ts DESC LIMIT 50")
    totals = q("SELECT endpoint, COUNT(*) AS n, SUM(credits) AS credits, "
               "ROUND(AVG(latency_ms)) AS ms, SUM(cache_hit) AS hits "
               "FROM api_calls GROUP BY endpoint ORDER BY n DESC")
    def candles(interval, key):
        # the deployed site.db has no candles; export_site.py leaves their freshness in meta
        try:
            v = q1("SELECT MAX(time_open) AS v FROM ohlcv WHERE interval = ?", interval)["v"]
        except sqlite3.OperationalError:
            v = None
        return v or meta(key)

    fresh = {
        "ratings": latest_ts(),
        "order books": (q1("SELECT MAX(ts) AS v FROM books") or {"v": None})["v"],
        "daily candles": candles("d", "fresh_daily"),
        "hourly candles": candles("h", "fresh_hourly"),
    }
    return render_template("debug.html", calls=calls, totals=totals, fresh=fresh)


@app.errorhandler(404)
def not_found(_):
    return render_template("404.html"), 404


# ---------------------------------------------------------------------------
# Public API -- versioned, rate-limited, always returns as_of
# ---------------------------------------------------------------------------

RATE_LIMIT = 60                         # requests per minute per IP
_hits = defaultdict(deque)


def _limited():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0]
    now, h = time.time(), _hits[ip]
    while h and h[0] < now - 60:
        h.popleft()
    h.append(now)
    return len(h) > RATE_LIMIT


def _rating_json(r, size=None):
    band = (r["max_pos_lo"], r["max_pos_hi"])
    out = {
        "id": r["token_id"], "symbol": r["symbol"], "name": r["name"], "slug": r["slug"],
        "grade": r["grade"],
        "max_position_usd": None if r["extrapolated"] else r["max_position"],
        "max_position_note": (f"above the ${impact.CALIBRATED_MAX_USD:,.0f} calibration limit"
                              if r["extrapolated"] else None),
        "max_position_band_50pct": None if r["extrapolated"] else band,
        "tolerance_bps": impact.TOLERANCE_BPS,
        "exit_100k_bps": r["exit_100k_bps"],
        "inputs": {"volume_24h": r["volume_24h"], "sigma_daily": r["sigma"],
                   "Y": r["Y"], "delta": r["delta"], "market_cap": r["market_cap"]},
        "as_of": r["ts"],
        "methodology": url_for("methodology", _external=True),
    }
    if size:
        ec = impact.exit_cost(size, r["volume_24h"], r["sigma"], r["Y"], r["delta"])
        out["exit"] = ec and {**ec, "band_bps_50pct": impact.band_bps(ec["bps"]),
                              "beyond_calibration": size > impact.CALIBRATED_MAX_USD}
    return out


@app.route("/api/v1/impact/<symbol>")
def api_impact(symbol):
    """?size=2000000 -> exit cost for that size, plus the token's rating.
    Symbols collide across tokens: pass ?id= (CMC id) or use the slug if you get a 409."""
    if _limited():
        return jsonify(error="rate limited", limit_per_minute=RATE_LIMIT), 429
    try:
        size = float(request.args["size"]) if "size" in request.args else None
    except ValueError:
        return jsonify(error="size must be a number of USD"), 400
    if size is not None and size <= 0:
        return jsonify(error="size must be positive"), 400
    ts = latest_ts()
    if request.args.get("id"):
        rows = q("SELECT * FROM ratings WHERE ts = ? AND token_id = ?", ts, request.args["id"])
    else:
        rows = q("SELECT * FROM ratings WHERE ts = ? AND (UPPER(symbol) = UPPER(?) OR slug = ?)",
                 ts, symbol, symbol.lower())
    if not rows:
        return jsonify(error=f"no rating for {symbol}", as_of=ts), 404
    if len(rows) > 1:
        return jsonify(error=f"{symbol} matches {len(rows)} tokens; pass ?id=",
                       candidates=[{"id": r["token_id"], "name": r["name"], "slug": r["slug"]}
                                   for r in rows], as_of=ts), 409
    return jsonify(_rating_json(rows[0], size))


@app.route("/api/v1/ratings")
def api_ratings():
    """Every rated token, largest market cap first."""
    if _limited():
        return jsonify(error="rate limited", limit_per_minute=RATE_LIMIT), 429
    rows = latest_ratings()
    return jsonify(as_of=latest_ts(), count=len(rows), ratings=[_rating_json(r) for r in rows])


if __name__ == "__main__":
    app.run(debug=bool(os.getenv("FLASK_DEBUG")), port=int(os.getenv("PORT", "5000")))
