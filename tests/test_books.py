"""The book walk is what every model number is graded against -- test it by hand.
pytest: https://docs.pytest.org/en/stable/
"""
import os
import pytest

os.environ.setdefault("CMC_API_KEY", "test")   # config.py fails loudly without it
from ingest.books import fill_price, walk_book, depth_within


BIDS = [(100.0, 10.0), (99.0, 10.0), (98.0, 10.0)]    # $1000, $990, $980 of depth


def test_fill_inside_best_level_has_zero_slippage():
    assert walk_book(BIDS, 500) == 0.0


def test_exactly_one_full_level_has_zero_slippage():
    assert walk_book(BIDS, 1000) == pytest.approx(0.0)


def test_partial_second_level_by_hand():
    # $1000 at 100 -> 10 units; $495 at 99 -> 5 units. avg = 1495 / 15
    avg = 1495 / 15
    assert fill_price(BIDS, 1495) == pytest.approx(avg)
    assert walk_book(BIDS, 1495) == pytest.approx(10_000 * (100 - avg) / 100)


def test_whole_book_fills_exactly():
    assert walk_book(BIDS, 2970) == pytest.approx(10_000 * (100 - 2970 / 30) / 100)


def test_too_thin_returns_none_not_zero():
    """None, never 0 -- zero would read as 'perfectly liquid' downstream."""
    assert walk_book(BIDS, 2971) is None
    assert walk_book([], 100) is None


def test_buy_side_is_symmetric():
    asks = [(100.0, 10.0), (101.0, 10.0)]
    avg = 1505 / (10 + 505 / 101)
    assert walk_book(asks, 1505) == pytest.approx(10_000 * (avg - 100) / 100)


def test_slippage_grows_with_size():
    vals = [walk_book(BIDS, s) for s in (100, 1200, 2500, 2970)]
    assert vals == sorted(vals)


def test_depth_within_band():
    assert depth_within(BIDS, mid=100.0, pct=0.015) == pytest.approx(1990)   # 100 and 99
    assert depth_within(BIDS, mid=100.0, pct=0.0) == pytest.approx(1000)
