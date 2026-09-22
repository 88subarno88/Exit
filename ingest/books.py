"""Public order-book snapshots = your GROUND TRUTH.

This is the file that makes the project defensible. Without it, "your numbers are
made up" is an unanswerable criticism. With it, you have a published error table.

All of these are FREE and need NO API KEY:
  Binance  https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints
  Kraken   https://docs.kraken.com/rest/#tag/Market-Data/operation/getOrderBook
  Coinbase https://docs.cdp.coinbase.com/exchange/reference/exchangerestapi_getproductbook
  OKX      https://www.okx.com/docs-v5/en/#order-book-trading-market-data

Some are geo-restricted. Two or three that respond from your location is plenty.

Order books: https://en.wikipedia.org/wiki/Order_book
"""

# import requests


# def fetch_book(venue: str, symbol: str):
#     """Return {"bids": [(price, qty), ...], "asks": [...]}, best price first.
#
#     Each venue nests its response differently -- normalise here so the rest of the
#     codebase never knows which exchange a book came from.
#
#     e.g. Binance: GET https://api.binance.com/api/v3/depth?symbol=BTCUSDT&limit=5000
#     """
#     ...


# def walk_book(bids, size_usd):
#     """TRUE slippage: eat the book until `size_usd` is filled.
#
#     TODO:
#       best = bids[0][0]
#       remaining = size_usd; proceeds = 0
#       for price, qty in bids:
#           take = min(remaining, price * qty)
#           proceeds += take; remaining -= take
#           if remaining <= 0: break
#       if remaining > 0: return None   # book too thin -- that is a RESULT, record it
#       avg = proceeds / (size filled in units)
#       return 10_000 * (best - avg) / best     # bps
#
#     This number is what the model gets graded against. Get it exactly right;
#     an off-by-one here silently poisons the entire calibration.
#     """
#     ...


# def snapshot_all(symbols, sizes=(10_000, 100_000, 1_000_000, 10_000_000)):
#     """Run DAILY from day 2. Write rows to `books`.
#
#     ~250 symbols x 10 days x 4 sizes ~= 10,000 calibration rows. That is a
#     comfortable tabular dataset -- and it only exists if you start early.
#     """
#     ...
