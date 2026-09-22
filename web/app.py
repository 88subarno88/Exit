"""The six surfaces. Flask: https://flask.palletsprojects.com/en/3.0.x/quickstart/

RULE: this file NEVER calls CoinMarketCap. It only reads SQLite.
If you break that rule, your demo dies when the tier expires on 30 Sep.

Charts: https://www.chartjs.org/docs/latest/
Interactivity without a JS build: https://htmx.org/docs/
"""

# from flask import Flask, render_template, jsonify, request
# app = Flask(__name__)


# @app.route("/")
# def map_view():
#     """SURFACE 1 -- THE MAP. Every token as a dot: size=mcap, colour=grade.
#     Headline sentence on top, e.g. "71% of tokens can't absorb $100k under 5%".
#     Precompute the layout in the worker and ship coordinates; do not lay out
#     thousands of nodes in the browser."""
#     ...


# @app.route("/token/<symbol>")
# def token(symbol):
#     """SURFACE 2 -- the product. Page anatomy (same on every page):
#            headline number -> evidence -> caveat -> link to /methodology
#
#       1. MAX SAFE POSITION, huge, with its confidence band
#       2. grade chip
#       3. cost curve (show the CLIFF)
#       4. venue table
#       5. inline what-if panel: "remove biggest venue" / "market -30%"
#          (this is where Stress lives -- an absorbed panel, not its own page)
#     """
#     ...


# @app.route("/ratings")
# def ratings():
#     """SURFACE 3 -- league table + downgrade feed, plus a "Real Cap" tab that
#     re-ranks by liquidity-adjusted cap with rank deltas.
#     The feed is your proof the system ran unattended. Show timestamps."""
#     ...


# @app.route("/hindsight")
# def hindsight():
#     """SURFACE 4 -- THE ONE THEY REMEMBER. The model run backwards through
#     LUNA/UST, FTT, CRV. Mark the collapse date on the chart and show liquidity
#     dying BEFORE the price did.
#
#     Honest caveat, stated on the page: market-pairs is latest-only, so historical
#     venue structure is inferred; volume and volatility are real. Say which is which.
#     """
#     ...


# @app.route("/methodology")
# def methodology():
#     """SURFACE 5 -- the model, the calibration, the BASELINE TABLE, the limits,
#     the feature importances. Can be plain. It earns credibility by being thorough,
#     not pretty."""
#     ...


# @app.route("/debug")
# def debug():
#     """SURFACE 6 -- last 50 API calls: endpoint, status, latency, credits, cache
#     hit. This satisfies the hackathon's "visible evidence of a real API call"
#     requirement better than any README snippet."""
#     ...


# ---- Public API: turns a website into infrastructure -----------------------
# @app.route("/api/v1/impact/<symbol>")
# def api_impact(symbol):
#     """?size=2000000 -> {exit_cost_bps, max_position_usd, grade, confidence, as_of}
#     Version it, document it, rate-limit it. Always return `as_of`."""
#     ...
