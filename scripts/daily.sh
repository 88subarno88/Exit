#!/usr/bin/env bash
# Everything that has to happen once a day. Run by hand or from cron:
#   0 9 * * * /home/vzux/Desktop/exit/scripts/daily.sh
# Output goes to data/daily_<date>.log.
set -u
cd "$(dirname "$0")/.."
PY=.venv/bin/python
LOG="data/daily_$(date +%F).log"

{
  echo "=== $(date -Is) daily run ==="
  echo "--- 1. order books (ground truth, ~15 min)"
  $PY -m ingest.books || echo "books FAILED"
  echo "--- 2. OHLCV top-up (hourly history only reaches back one month)"
  $PY scripts/backfill_ohlcv.py || echo "backfill FAILED"
  echo "--- 3. re-calibrate on all days so far"
  $PY -m ingest.calibrate || echo "calibrate FAILED"
  echo "--- 4. grade distribution"
  $PY scripts/grades.py || echo "grades FAILED"
  echo "=== done $(date -Is) ==="
} 2>&1 | tee -a "$LOG"
