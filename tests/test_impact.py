"""Tests. 15 points of the score is code quality, and most hackathon repos have zero.
pytest: https://docs.pytest.org/en/stable/
"""
import math
import pytest

from ingest.impact import (impact_bps, max_position, exit_cost, manipulation_cost,
                           cost_curve, sigma_daily, venue_features, grade, rate,
                           GRADE_SCALE)

# Fixed parameters, so the tests don't depend on whatever calibration.json holds.
V, SIG, Y, D = 5_000_000, 0.04, 0.8, 0.5


def test_impact_scales_as_sqrt():
    """delta = 0.5: 4x the size -> 2x the impact. If this fails, the formula is wrong."""
    assert impact_bps(400_000, V, SIG, Y, 0.5) == pytest.approx(2 * impact_bps(100_000, V, SIG, Y, 0.5))


def test_impact_scales_linearly_at_delta_one():
    assert impact_bps(400_000, V, SIG, Y, 1.0) == pytest.approx(4 * impact_bps(100_000, V, SIG, Y, 1.0))


def test_impact_by_hand():
    # 10_000 * 0.8 * 0.04 * sqrt(50k / 5M) = 320 * 0.1 = 32 bps
    assert impact_bps(50_000, V, SIG, Y, 0.5) == pytest.approx(32.0)
    # delta = 0.75: 320 * 0.01 ** 0.75 = 320 * 0.031623 = 10.119
    assert impact_bps(50_000, V, SIG, Y, 0.75) == pytest.approx(320 * 0.01 ** 0.75)


def test_zero_volume_returns_none():
    """Untradeable must be None -- not zero, not infinity. Zero silently becomes
    'perfectly liquid' downstream, which is the worst possible bug here."""
    assert impact_bps(10_000, 0, SIG, Y) is None
    assert impact_bps(10_000, None, SIG, Y) is None
    assert impact_bps(10_000, V, None, Y) is None
    assert max_position(0, SIG, Y) is None
    assert exit_cost(10_000, 0, SIG, Y) is None
    assert grade(max_position(0, SIG, Y)) == "NR"


def test_max_position_inverts_impact():
    """impact_bps(max_position(tol)) == tol. The two must be exact inverses;
    the whole site shows both numbers and they cannot disagree."""
    for d in (0.3, 0.5, 0.8, 1.2):
        for tol in (10, 200, 1000):
            q = max_position(V, SIG, Y, tol, delta=d)
            assert impact_bps(q, V, SIG, Y, d) == pytest.approx(tol)


def test_exit_cost_flags_beyond_volume_and_caps_at_total_loss():
    small = exit_cost(100_000, V, SIG, Y, D)
    assert not small["beyond_model"]
    assert small["cost_usd"] == pytest.approx(100_000 * small["bps"] / 10_000)
    huge = exit_cost(1e12, V, SIG, Y, D)
    assert huge["beyond_model"] and huge["bps"] == 10_000


def test_manipulation_moves_marginal_price_by_target():
    """Marginal price at the end of the buy = (1 + delta) x the average cost."""
    for d in (0.5, 0.9):
        m = manipulation_cost(V, SIG, Y, target_move_pct=10, delta=d)
        avg = impact_bps(m["size_usd"], V, SIG, Y, d)
        assert (1 + d) * avg == pytest.approx(1000)
        assert m["cost_usd"] == pytest.approx(m["size_usd"] * avg / 10_000)


def test_marginal_factor_by_finite_difference():
    """Check (1 + delta) numerically: d(Q * avg)/dQ vs (1 + delta) * avg."""
    d, q, h = 0.8, 300_000, 1.0
    total = lambda s: s * impact_bps(s, V, SIG, Y, d)
    assert (total(q + h) - total(q - h)) / (2 * h) == pytest.approx((1 + d) * impact_bps(q, V, SIG, Y, d), rel=1e-6)


def test_cost_curve_is_monotonic_and_reaches_the_cliff():
    c = cost_curve(V, SIG, Y, delta=D)
    bps = [b for _, b, _ in c]
    assert bps == sorted(bps)
    assert c[-1][2] is True           # the last point is past 1x volume, flagged
    assert cost_curve(0, SIG, Y) == []


def test_sigma_of_constant_returns_is_zero_vol_none_and_known_value():
    assert sigma_daily([100] * 30) is None                 # no movement -> no sigma
    assert sigma_daily([1, 2, 3]) is None                  # too short
    closes = [100 * math.exp(0.01 * (i % 2)) for i in range(21)]   # +1%, -1%, ...
    assert sigma_daily(closes) == pytest.approx(0.01, rel=0.05)


def test_hhi_single_venue_is_one():
    """One venue with all volume -> HHI == 1.0."""
    f = venue_features([{"venue": "binance", "volume_24h": 1e6}])
    assert f["hhi"] == 1.0 and f["pair_count"] == 1 and f["top_venue_share"] == 1.0


def test_hhi_equal_split():
    f = venue_features([{"venue": v, "volume_24h": 1e6} for v in "abcd"])
    assert f["hhi"] == pytest.approx(0.25)


def test_dead_pairs_excluded():
    """Near-zero-volume pairs must not inflate pair_count -- otherwise a token
    with 40 dead listings looks liquid."""
    rows = [{"venue": "binance", "volume_24h": 1e6}] + \
           [{"venue": f"dead{i}", "volume_24h": 5} for i in range(40)]
    f = venue_features(rows)
    assert f["pair_count"] == 1 and f["hhi"] == 1.0


def test_two_pairs_on_one_venue_count_once_and_dex_share():
    f = venue_features([{"venue": "uni", "venue_type": "dex", "volume_24h": 3e5},
                        {"venue": "uni", "venue_type": "dex", "volume_24h": 1e5},
                        {"venue": "binance", "venue_type": "cex", "volume_24h": 6e5}])
    assert f["pair_count"] == 2
    assert f["dex_share"] == pytest.approx(0.4)


def test_grade_thresholds_and_concentration_penalty():
    assert grade(50_000_000) == "AAA"
    assert grade(5_000) == "D"
    assert grade(2_000_000) == "A"
    assert grade(2_000_000, hhi=0.95) == "BBB"            # one notch down
    assert grade(2_000_000, pair_count=1) == "BBB"
    assert grade(5_000, hhi=1.0) == "D"                   # can't go below D
    floors = [f for _, f in GRADE_SCALE]
    assert floors == sorted(floors, reverse=True)


def test_rate_readings_agree():
    """All four readings come from one curve, so they must be consistent."""
    r = rate(V, SIG, Y, exit_size_usd=250_000, delta=0.7)
    assert impact_bps(r["max_position_usd"], V, SIG, Y, 0.7) == pytest.approx(200)
    assert r["exit_cost"]["bps"] == pytest.approx(impact_bps(250_000, V, SIG, Y, 0.7))
    assert r["grade"] == grade(r["max_position_usd"])


def test_max_position_beyond_calibration_is_flagged():
    assert rate(5e10, 0.02, 1.0, delta=0.5)["max_position_extrapolated"] is True
    assert rate(1e6, 0.08, 1.0, delta=0.5)["max_position_extrapolated"] is False
    assert rate(0, 0.08, 1.0)["max_position_extrapolated"] is False
