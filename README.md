# EXIT — liquidity intelligence for crypto

> Market cap tells you what a token claims to be worth. Exit tells you what you
> could actually get.

**This repo is a guided scaffold.** Implementations are left as commented hints for
you to fill in. Start with [`GUIDE.md`](GUIDE.md).

Full project spec: `../CMC_Hackathon/EXIT.md`

## Quick start

```bash
cp .env.example .env          # add your CMC key
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/day1_validate.py    # the go/no-go check — run this first
```

## Layout

```
GUIDE.md                  step-by-step build order, with links to learn each piece
scripts/day1_validate.py  go/no-go check (written for you — run it today)
ingest/config.py          env + TTLs                      (start here)
ingest/cache.py           SQLite + TTL + stale fallback   (saves your demo)
ingest/cmc.py             CMC client + call logging
ingest/schema.sql         tables
ingest/books.py           public order books = ground truth
ingest/impact.py          THE MODEL — one curve, four readings
ingest/calibrate.py       fit Y, baseline vs learned
ingest/worker.py          scheduler (start it early — history accrues)
web/app.py                six surfaces + public API
tests/test_impact.py      the maths must be right
```

## Before you commit anything

- [ ] `.gitignore` committed **first** — a key in git history still counts against you
- [ ] `.env` never staged
