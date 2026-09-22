"""The price impact model. This file IS the project — everything else serves it.

The square-root law of market impact:

    dP/P  ~=  Y * sigma * sqrt(Q / V)

    Q     = order size in USD
    V     = 24h volume in USD           (CMC)
    sigma = daily volatility            (CMC OHLCV)
    Y     = impact constant             <- the ONLY unknown. calibrate.py learns it.

Read before writing this:
  - https://en.wikipedia.org/wiki/Market_impact
  - Almgren, Thum, Hauptmann & Li, "Direct Estimation of Equity Market Impact" (2005)
    -- search the title, several university copies are online. This is the paper
       the square-root law comes from. Cite it in METHODOLOGY.md.
  - HHI for concentration: https://en.wikipedia.org/wiki/Herfindahl%E2%80%93Hirschman_index

Everything the site shows is this one curve read four ways. Keep that literal —
write ONE function for the curve and derive the rest from it.
"""

# import math


# def impact_bps(size_usd, volume_24h, sigma_daily, Y):
#     """Forward: how far does price move if I sell `size_usd`?
#
#     TODO: return 10_000 * Y * sigma_daily * math.sqrt(size_usd / volume_24h)
#
#     Guard the edges before you trust it:
#       - volume_24h <= 0  -> untradeable, return None (NOT infinity, and NOT zero)
#       - size >> volume   -> the formula stops being meaningful past ~1x daily volume.
#                             Cap it and flag it rather than printing 400%.
#     """
#     ...


# def max_position(volume_24h, sigma_daily, Y, tolerance_bps=200):
#     """Inverse #1 -- THE HERO NUMBER. "How much can I safely hold?"
#
#     Solve impact_bps(Q) = tolerance for Q:
#         Q = V * (tolerance / (10_000 * Y * sigma)) ** 2
#
#     This is the primary output because it answers the question BEFORE you buy,
#     which is where the decision actually happens. Buyers outnumber trapped holders.
#     """
#     ...


# def manipulation_cost(volume_24h, sigma_daily, Y, target_move_pct=10):
#     """Inverse #2 -- the viral number. "What does it cost to move this 10%?"
#
#     Same algebra as max_position with the target as the tolerance. Then convert
#     the required size into the attacker's actual cost (they must buy, and they
#     move the price against themselves on the way in).
#     """
#     ...


# def cost_curve(volume_24h, sigma_daily, Y, sizes=None):
#     """The chart. impact_bps over a log-spaced range of sizes.
#     Returns [(size_usd, bps), ...] -- feed straight to Chart.js.
#     The visual point is the CLIFF: where the curve goes vertical."""
#     ...


# ---------------------------------------------------------------------------
# Structural features. Inputs to the grade, and features for the ML in calibrate.py
# ---------------------------------------------------------------------------

# def venue_features(pairs_rows):
#     """From this token's rows in `pairs`, compute:
#         pair_count       -- how many active venues
#         hhi              -- sum((venue_vol / total_vol) ** 2). 1.0 = one venue only.
#         top_venue_share  -- the single scariest number for fragility
#         cex_dex_split
#         total_volume
#     Filter dead pairs first (near-zero volume) or HHI is meaningless.
#     """
#     ...


# def grade(max_pos_usd, hhi, pair_count):
#     """AAA -> D. Keep the thresholds in ONE dict here, and print that dict on
#     /methodology. A transparent, arguable scale beats a black box: a judge cannot
#     fault a method they can see, and they WILL test one token by hand.
#     """
#     ...
