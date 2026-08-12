# Running the collector every hour on a Mac

## Use the project venv, not whatever `python` resolves to

```bash
cd ~/Projects/bkk-flood-forecast
source .venv/bin/activate          # anaconda's python is missing duckdb
PYTHONPATH=src python -m pytest tests/test_collectors.py -q   # 30 passed
```

The collectors themselves only need **`requests`, `pandas` and `pyarrow`** —
`bkkflood/__init__.py` resolves names on first use, so importing
`bkkflood.collectors` no longer drags in duckdb, LightGBM and rasterio. That
matters for the always-on box below: it does not need the modelling stack
installed just to poll four APIs.

## Install

```bash
chmod +x scripts/run_live_collect.sh

# Test it once by hand first. Never schedule something you have not seen work.
./scripts/run_live_collect.sh
cat data/live/_logs/collect-$(date -u +%Y-%m-%d).log
```

If that produced files under `data/live/thaiwater/`, schedule it:

```bash
cp scripts/com.bkkflood.livecollect.plist ~/Library/LaunchAgents/
launchctl load  ~/Library/LaunchAgents/com.bkkflood.livecollect.plist
launchctl list | grep bkkflood          # should appear
```

## Check on it

```bash
# Did the last run work? One file, no log-reading.
cat data/live/_status.json | python3 -m json.tool | head -30

# Latest run log
tail -40 data/live/_logs/collect-$(date -u +%Y-%m-%d).log

# How much history exists, and are we past cold start
PYTHONPATH=src python3 -c "
from bkkflood.collectors import coverage_report
print(coverage_report().to_string(index=False))"
```

## Stop it

```bash
launchctl unload ~/Library/LaunchAgents/com.bkkflood.livecollect.plist
```

---

## The catch with running this on a laptop

**launchd does not run while the Mac is asleep.** Close the lid overnight and you
get a gap. `StartInterval` fires once on wake, so you get one reading instead of
the eight you missed — and those eight hours cannot be back-filled, because
ThaiWater has no history endpoint.

For a few weeks of proving the pipeline works, that is fine. For the season of
history that actually makes this worth doing, it is not. Options, cheapest first:

1. **`caffeinate`** or Settings → Battery → *Prevent automatic sleeping when the
   display is off* (only helps while plugged in).
2. **A small always-on box** — a Raspberry Pi or a $5/month VPS. The collector is
   a few hundred lines of Python and one hourly cron line:
   ```cron
   7 * * * * /home/you/bkk-flood-forecast/scripts/run_live_collect.sh
   ```
   Minute 7 rather than 0 on purpose — it avoids the moment every scheduled job
   on the internet hits an API at once.

Whatever you pick, check `coverage_report()` weekly. A collector everyone assumes
is running, and is not, is worse than no collector: you find out months later
that the season you were counting on has holes in it.

---

## What gets written

```
data/live/
  thaiwater/dt=2026-08-11/part-20260811T090000Z.parquet    <- tidy table
  openmeteo/dt=2026-08-11/part-20260811T090000Z.parquet
  traffy/dt=2026-08-11/part-20260811T090000Z.parquet
  pumps/dt=2026-08-11/part-20260811T090000Z.parquet
  _raw/thaiwater/dt=2026-08-11/20260811T090000Z.json.gz    <- untouched response
  _reference/thaiwater_station_coords.csv                  <- real coordinates
  _status.json                                             <- last run health
  _runs/run-20260811T090000Z.ipynb                         <- executed notebook
  _logs/collect-2026-08-11.log
```

`_status.json` is the one file here that IS overwritten each run. It describes
*now*, it is not a record of anything, and it can be rebuilt from the parquet.
Everything else is append-only.

Read it all back with DuckDB, the same way the rest of the project reads parquet:

```sql
SELECT * FROM read_parquet('data/live/thaiwater/**/*.parquet');
```

**Nothing is ever overwritten.** Each poll writes a new file. This directory is
not a cache of something we could re-download — it *is* the historical record,
and it exists only because the collector ran.

### Add this to `.gitignore`

```
data/live/
```

The parquet files will grow steadily and they are data, not code. Back them up
separately — losing them means losing time, not just bytes.
