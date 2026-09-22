# Build guide — EXIT

Work through these in order. Do not skip step 0 or step 2.

> Links were correct when written (2026-09-20). If one 404s, search the title.

---

## Step 0 — Accounts and keys  *(30 min, do today)*

1. Create a CoinMarketCap API account → https://coinmarketcap.com/api
2. Register on DoraHacks using **the same email as your CMC account**
   → https://dorahacks.io/hackathon/coinmarketcap-api-202609
3. Copy `.env.example` to `.env`, paste your key in.
4. `git init` and commit `.gitignore` **first**, before anything else.
   A key in git history is still there after you delete it, and the rules say it
   counts against you.

```bash
cp .env.example .env     # then edit .env
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

---

## Step 1 — Read the API docs  *(1 hour)*

- Main docs → https://coinmarketcap.com/api/documentation/v1/
- The endpoint everything depends on: **market-pairs/latest**. Find it in the docs and
  read what fields it returns.
- DEX v4 endpoints (spot-pairs, pairs/quotes) — skim.
- Rate limits and credit costs → https://coinmarketcap.com/api/documentation/v1/#section/Standards-and-Conventions

**What you're looking for:** does `market-pairs/latest` give you, per venue, both the
**volume** and the **price**? Everything rests on that.

---

## Step 2 — The go/no-go check  *(1 hour)*

```bash
python scripts/day1_validate.py
```

This is written for you — it's a diagnostic, not part of the product. It pulls
market-pairs for ten tokens across the cap spectrum and prints what you actually get.

**Read the output carefully.** If per-venue volume and price are there, build Exit.
If they're missing or nearly empty, stop and rethink before writing anything else.

---

## Step 3 — Ingest skeleton  *(day 1–2)*

Fill in, in this order:

1. `ingest/config.py` — trivial, do it first
2. `ingest/cache.py` — SQLite + TTL + **stale fallback**
3. `ingest/cmc.py` — the client, with call logging and credit accounting
4. `ingest/schema.sql` — run it once to create tables

Then get `worker.py` pulling listings + market-pairs into SQLite on a loop.

**Start the worker running as soon as it works.** Intraday liquidity patterns and the
downgrade feed only exist if you've been sampling since early. Every day you don't run
it is a day of history you can't get back.

Learn:
- sqlite3 → https://docs.python.org/3/library/sqlite3.html
- requests → https://requests.readthedocs.io/en/latest/
- APScheduler → https://apscheduler.readthedocs.io/en/3.x/

---

## Step 4 — Order book snapshots  *(day 2, runs in background from then on)*

`ingest/books.py`. Public, free, no auth needed:

- Binance → https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints
- Kraken → https://docs.kraken.com/rest/#tag/Market-Data/operation/getOrderBook
- Coinbase → https://docs.cdp.coinbase.com/exchange/reference/exchangerestapi_getproductbook
- OKX → https://www.okx.com/docs-v5/en/#order-book-trading-market-data

Some are geo-restricted. Use whichever two or three respond from where you are.

This is your **ground truth**. Without it the whole model is unvalidated and a judge
can dismiss it in one sentence.

---

## Step 5 — The impact model  *(day 3)*

`ingest/impact.py`. The square-root law:

```
ΔP/P  ≈  Y · σ · sqrt(Q / V)
```

Learn:
- Market impact → https://en.wikipedia.org/wiki/Market_impact
- The canonical paper: Almgren, Thum, Hauptmann, Li — *"Direct Estimation of Equity
  Market Impact"* (2005). Search the title; several university copies are online.
- Optimal execution / Almgren–Chriss → https://en.wikipedia.org/wiki/Algorithmic_trading
  (search "Almgren-Chriss optimal execution" for the original)
- HHI, for volume concentration → https://en.wikipedia.org/wiki/Herfindahl%E2%80%93Hirschman_index

---

## Step 6 — Calibration  *(day 4)*

`ingest/calibrate.py`. Walk each real order book to get **true** slippage, fit `Y`,
report the error.

**Publish the table even if the result is unflattering.** A stated baseline you beat by
a little is worth more than an unstated one you claim to beat by a lot.

Learn:
- Walking an order book → https://en.wikipedia.org/wiki/Order_book
- scikit-learn ensembles → https://scikit-learn.org/stable/modules/ensemble.html
- **Group cross-validation** (split by token, not by row — this matters a lot)
  → https://scikit-learn.org/stable/modules/cross_validation.html#group-k-fold

---

## Step 7 — The web app  *(day 5 — deploy today, not later)*

`web/app.py`. Six surfaces: Map, token page, Ratings, Hindsight, Methodology, Debug.

- Flask → https://flask.palletsprojects.com/en/3.0.x/quickstart/
- HTMX (if you want interactivity without a JS build) → https://htmx.org/docs/
- Chart.js → https://www.chartjs.org/docs/latest/
- Deploy: Render → https://render.com/docs/deploy-flask ·
  Fly.io → https://fly.io/docs/languages-and-frameworks/python/

**Deploy the moment one page renders.** Everything after that is iteration on something
already public.

---

## Step 8 — API + MCP  *(day 6)*

- MCP spec → https://modelcontextprotocol.io/
- Python SDK → https://github.com/modelcontextprotocol/python-sdk
- Adding a server to Claude Code → https://docs.claude.com/en/docs/claude-code/mcp

Install your own server into Claude Code and ask it *"can I get out of $2M of BONK?"*
That exchange is your best video moment.

---

## Step 9 — Freeze, polish, document, present  *(day 7+)*

No new features after the freeze. Run the checklist in
`../CMC_Hackathon/26_POLISH.md`, then README → Methodology → API_FEEDBACK → video →
submit → tweet with `#BuildwithCMC`.
