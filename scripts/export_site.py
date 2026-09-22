#!/usr/bin/env python3
"""Copy what the website reads into a small web/site.db for deployment.

Run:  python scripts/export_site.py        (daily.sh runs it last)

The working DB (data/exit.db) holds raw candles and order books -- 100MB+ and
never needed by a page. The site needs ratings, the evidence dots, the latest
venue table, Hindsight, and the API-call log. Deploy web/site.db with the code;
after 30 Sep, when the CMC tier lapses, the site keeps serving the last export.
"""
import os, sys, sqlite3, datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, os.getenv("DB_PATH", "data/exit.db"))
DST = os.path.join(ROOT, "web", "site.db")

TABLES = {
    "ratings":        "SELECT * FROM src.ratings",
    "observed_costs": "SELECT * FROM src.observed_costs",
    "books":          """SELECT b.* FROM src.books b
                         JOIN (SELECT token_id, MAX(ts) AS ts FROM src.books GROUP BY token_id) l
                           ON l.token_id = b.token_id AND l.ts = b.ts
                         WHERE b.side = 'sell' AND b.size_usd = 100000""",
    "hindsight":      "SELECT * FROM src.hindsight",
    "meta":           "SELECT * FROM src.meta",
    "api_calls":      "SELECT * FROM src.api_calls ORDER BY ts DESC LIMIT 1000",
}


def main():
    if not os.path.exists(SRC):
        sys.exit(f"{SRC} not found -- run the pipeline first.")
    tmp = DST + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    out = sqlite3.connect(tmp)
    with open(os.path.join(ROOT, "ingest", "schema.sql")) as f:
        out.executescript(f.read())
    out.execute("ATTACH DATABASE ? AS src", (f"file:{SRC}?mode=ro",))
    for table, sql in TABLES.items():
        out.execute(f"INSERT INTO main.{table} {sql}")
    # /debug shows candle freshness; the candles themselves stay behind
    for key, sql in (("fresh_daily", "SELECT MAX(time_open) FROM src.ohlcv WHERE interval='d'"),
                     ("fresh_hourly", "SELECT MAX(time_open) FROM src.ohlcv WHERE interval='h'"),
                     ("exported_at", "SELECT ?")):
        args = (dt.datetime.now(dt.timezone.utc).isoformat(),) if key == "exported_at" else ()
        v = out.execute(sql, args).fetchone()[0]
        out.execute("INSERT OR REPLACE INTO main.meta VALUES (?, json_quote(?))", (key, v))
    out.commit()
    out.execute("DETACH DATABASE src")
    out.execute("VACUUM")
    out.close()
    os.replace(tmp, DST)                 # atomic: a running site never sees half a file
    print(f"Wrote {os.path.relpath(DST, ROOT)} ({os.path.getsize(DST) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
