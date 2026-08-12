#!/bin/bash
# Run the live collectors once. Intended for launchd/cron.
#
# Executes notebooks/10_live_collect.ipynb so the project rule "scripts live as
# notebooks" still holds, and so every scheduled run leaves an executed copy in
# data/live/_runs/ that you can open and read like a log.
#
# If nbconvert is not installed it falls back to calling the collectors directly,
# because a missing dev dependency must not cost an hour of data that cannot be
# re-fetched.

set -uo pipefail

REPO="${BKKFLOOD_REPO:-$HOME/Projects/bkk-flood-forecast}"
cd "$REPO" || { echo "repo not found: $REPO" >&2; exit 1; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUNS="$REPO/data/live/_runs"
LOGS="$REPO/data/live/_logs"
mkdir -p "$RUNS" "$LOGS"
LOG="$LOGS/collect-$(date -u +%Y-%m-%d).log"

echo "=== $STAMP starting ===" >>"$LOG"

# Use the project venv if it exists.
if [ -f "$REPO/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$REPO/.venv/bin/activate"
fi

PY="${PYTHON:-python3}"
export PYTHONPATH="$REPO/src:${PYTHONPATH:-}"

# Pin the repo root explicitly. Without it the collector resolves its own root
# from __file__, which is correct here but silently wrong the day someone runs
# this from a copy — and history written to the wrong tree looks exactly like
# history that was never written.
export BKKFLOOD_REPO="$REPO"

if "$PY" -c "import nbconvert" >/dev/null 2>&1; then
  "$PY" -m jupyter nbconvert \
      --to notebook --execute \
      --ExecutePreprocessor.timeout=600 \
      --output "$RUNS/run-$STAMP.ipynb" \
      notebooks/10_live_collect.ipynb >>"$LOG" 2>&1
  RC=$?
else
  echo "nbconvert not installed - calling collectors directly" >>"$LOG"
  "$PY" -c "
from bkkflood.collectors import collect_all, results_table
print(results_table(collect_all()).to_string(index=False))
" >>"$LOG" 2>&1
  RC=$?
fi

if [ $RC -eq 0 ]; then
  echo "=== $STAMP ok ===" >>"$LOG"
else
  echo "=== $STAMP FAILED rc=$RC ===" >>"$LOG"
fi

# Keep the run notebooks from growing without bound: 14 days is plenty to debug
# a bad run, and the parquet files are the actual record.
find "$RUNS" -name 'run-*.ipynb' -mtime +14 -delete 2>/dev/null

exit $RC
