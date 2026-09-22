"""Tests. 15 points of the score is code quality, and most hackathon repos have zero.
pytest: https://docs.pytest.org/en/stable/
"""

# from ingest.impact import impact_bps, max_position, venue_features


# def test_impact_scales_as_sqrt():
#     """4x the size -> 2x the impact. If this fails, the formula is wrong."""
#     ...


# def test_zero_volume_returns_none():
#     """Untradeable must be None -- not zero, not infinity. Zero silently becomes
#     'perfectly liquid' downstream, which is the worst possible bug here."""
#     ...


# def test_max_position_inverts_impact():
#     """impact_bps(max_position(tol)) == tol. The two must be exact inverses;
#     the whole site shows both numbers and they cannot disagree."""
#     ...


# def test_hhi_single_venue_is_one():
#     """One venue with all volume -> HHI == 1.0."""
#     ...


# def test_dead_pairs_excluded():
#     """Near-zero-volume pairs must not inflate pair_count -- otherwise a token
#     with 40 dead listings looks liquid."""
#     ...
