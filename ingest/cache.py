"""SQLite cache with TTL and STALE FALLBACK.

Why this file is not optional
-----------------------------
Your free Startup tier expires when submissions close on 30 Sep. Judging runs
1-16 Oct. If the site calls CMC live with no fallback, judges see a dead app.

Rule: on a cache miss AND an upstream failure, serve the stale row with a visible
"last updated" timestamp. Never raise to the page.

Learn: https://docs.python.org/3/library/sqlite3.html
"""

# import sqlite3, json, time
# from .config import DB_PATH


# def _conn():
#     # TODO: sqlite3.connect(DB_PATH); consider check_same_thread=False if the
#     # web app and the worker share a process.
#     ...


# def get(key: str, ttl: int):
#     """Return (value, age_seconds, is_stale) or (None, None, None) if never cached.
#
#     TODO:
#       1. SELECT value, fetched_at FROM kv WHERE key = ?
#       2. age = now - fetched_at
#       3. return (json.loads(value), age, age > ttl)
#     Note it returns stale rows rather than hiding them — the CALLER decides.
#     """
#     ...


# def put(key: str, value) -> None:
#     """INSERT OR REPLACE INTO kv(key, value, fetched_at) VALUES (?, ?, ?)."""
#     ...


# def cached(key: str, ttl: int, fetch_fn):
#     """The pattern the whole project uses.
#
#       fresh hit            -> return it
#       stale hit, fetch ok  -> store and return new
#       stale hit, fetch dies-> return STALE (this is the line that saves your demo)
#       no hit,    fetch dies-> re-raise, nothing else to do
#     """
#     ...
