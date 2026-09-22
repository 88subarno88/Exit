"""Fit Y against real order books, then generalise to tokens that have none.

Two jobs:
  1. BASELINE  -- one global Y for the whole market.
  2. LEARNED   -- predict Y per token from structural features.

Job 2 is the one that actually justifies ML: most tokens have NO public order book
(DEX-only, small venues, long tail). Train on what you CAN measure, generalise to
what you cannot. That is the bridge from rating 250 tokens to rating 5,000 -- say
exactly that in the README, it is a much better justification than "we used ML".

Learn:
  https://scikit-learn.org/stable/modules/ensemble.html
  https://scikit-learn.org/stable/modules/cross_validation.html#group-k-fold
"""

# import numpy as np
# from sklearn.ensemble import GradientBoostingRegressor
# from sklearn.model_selection import GroupKFold


# def implied_Y(true_bps, size_usd, volume_24h, sigma_daily):
#     """Invert the square-root law to get the Y that WOULD have produced the
#     observed slippage:  Y = true_bps / (10_000 * sigma * sqrt(Q/V))"""
#     ...


# def fit_global_Y(rows):
#     """THE BASELINE. Median of implied_Y (median, not mean -- outliers will eat you).
#     You must beat this or you ship this. Either outcome is publishable."""
#     ...


# def fit_learned_Y(rows):
#     """Features -> Y. GradientBoostingRegressor is the right default here.
#
#     Features: pair_count, hhi, top_venue_share, cex_dex_split, log(mcap),
#               log(volume), sigma, token_age_days, sector
#
#     !! THE MISTAKE THAT WILL FOOL YOU !!
#     Cross-validate by TOKEN, not by row. Ten rows from the same token are not ten
#     independent observations -- random splits leak the same token into train and
#     test and your R^2 will look wonderful and mean nothing.
#         GroupKFold(n_splits=5).split(X, y, groups=token_ids)
#     """
#     ...


# def report(baseline, learned, holdout):
#     """Print the table that goes straight into METHODOLOGY.md:
#
#         | model           | median abs err | R^2 |
#         | global Y = 0.87 |      X bps     |  -  |
#         | learned Y       |      Y bps     | 0.- |
#
#     If learned does not beat baseline, SAY SO AND SHIP THE BASELINE. A published
#     negative result reads as scientific honesty. Concealed overfitting, once a
#     judge spots it, ends your run.
#
#     Also print feature_importances_ -- "venue concentration predicts slippage
#     better than market cap does" is itself a finding worth putting on /findings.
#     """
#     ...
