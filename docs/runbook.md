# Runbook — what the model does, how to run it, how to test it

Everything here was checked against the repository on 2026-08-11. The venv has
`fastapi`, `uvicorn`, `lightgbm` and `duckdb`; `data/features/features_2019…2025.parquet`
are all present; `frontend/node_modules` is already installed. It should start
without any setup.

---

## 1. What the model actually does

**The one question it answers**, and it is narrower than "will Bangkok flood":

> *This road is below 15 cm of water right now — will it reach 15 cm within the
> next 1 hour?*

Everything else the dashboard shows is built on top of that one prediction.

**What it takes in** (50 features, per road sensor, every 15 minutes):

- district rainfall from BMA's gauges — now, and over 1/3/6/24 h
- GFS forecast rain for the next 1/3/6 h
- canal water level and flow (city-wide averages, because we have no canal
  coordinates)
- the road sensor's own recent depth history — this is 87% of what the model uses
- terrain from the 1 m elevation model, tide phase, calendar

**What it puts out**, per station:

- a calibrated probability that the road crosses 15 cm within the hour
- a tier: below 5 cm / 5 / 15 / 30 cm
- a CAP 1.2 alert message for stations above threshold

**What it deliberately does not output:** a predicted depth in centimetres. The
depth intervals failed their coverage test, so severity comes from which
threshold is crossed, never from a predicted number.

### How good it is, in one table

| Measure | Value |
|---|---|
| Real flood events flagged before the water arrived (2025) | **53 in 100** |
| Recall on dry roads | 23% |
| Precision | 16% |
| Median warning time | **15 minutes** |
| Detections giving only one 15-min step of warning | 75% |
| Alert episodes per flood correctly warned | 6.6 |
| A simple "district rain over a threshold" rule, same metric | 22% |

Read the last two rows together. It beats a rainfall threshold by about one
point, and it raises roughly seven alerts for every flood it catches. **This is a
detection system, not yet a warning system**, and the limit is the data rather
than the method.

### Three limits to state before showing anyone

1. **It replays history.** There is no live path yet. Every response carries
   `data_mode: "replay"` and the timestamp it is answering for.
2. **1 hour only.** The 3-hour and 6-hour models were never saved — see
   `docs/project_status_2026-08-11.md`.
3. **It cannot say which road.** When a district floods, only ~35% of its
   stations do, and every rainfall, canal and terrain input is identical across
   them. District-level is the honest resolution.

---

## 2. Run it

Two terminals, from the repo root.

```bash
# terminal 1 — the API
source .venv/bin/activate
export PYTHONPATH="$PWD/src:$PWD"
uvicorn backend.app.main:app --reload
```

```bash
# terminal 2 — the dashboard
cd frontend
npm run dev          # node_modules is already installed
```

Then open **http://127.0.0.1:5173** for the dashboard, or
**http://127.0.0.1:8000/docs** for the interactive API.

The dashboard opens on **13 November 2025, 03:00** — a real flood, 29 stations
alerting and 25 already under water. That default is deliberate: the last
timestamp in the data is dry-season, and opening on a quiet moment makes a
working dashboard look broken.

---

## 3. Test it

### The test suite — start here

```bash
source .venv/bin/activate
PYTHONPATH=src python -m pytest -q
```

118 tests across 7 files, a few seconds. If this is green the library is sound.

### Poke the API by hand

```bash
# Is it alive, and what window can it answer for?
curl -s localhost:8000/health | python -m json.tool

# What can this model do, in its own words — read this before trusting output
curl -s localhost:8000/api/model-card | python -m json.tool

# A real flood: how many stations were alerting?
curl -s "localhost:8000/api/forecast?ts=2025-11-13%2003:00:00" \
  | python -c "import json,sys; d=json.load(sys.stdin); print(d['counts']); print('mode:', d['data_mode'])"

# Only the stations actually alerting
curl -s "localhost:8000/api/forecast?ts=2025-11-13%2003:00:00&alerting_only=true" \
  | python -c "import json,sys; d=json.load(sys.stdin)
for s in d['stations'][:10]: print(f\"{s['station_code']:<12} {s['district']:<18} p={s['probability']:.3f}\")"

# District roll-up — what the map draws
curl -s "localhost:8000/api/risk?ts=2025-11-13%2003:00:00" | python -m json.tool | head -30

# The CAP alert messages
curl -s "localhost:8000/api/alerts?ts=2025-11-13%2003:00:00" | python -m json.tool | head -40
```

### A real check, not a smoke test

A response that looks plausible is not the same as a correct one. Compare what
the model said against what actually happened:

```bash
source .venv/bin/activate
PYTHONPATH=src python - <<'PY'
import pandas as pd
from bkkflood import serving

ts = "2025-11-13 03:00:00"
f = serving.forecast_at(ts)
df = pd.DataFrame(f["stations"])

print(f"mode={f['data_mode']}  ts={f['timestamp']}  tier={f['tier_cm']}cm  horizon={f['horizon_hours']}h")
print(f"{len(df)} stations, {int(df.alerting.sum())} alerting\n")
print(df.nlargest(10, "probability")[
      ["station_code", "district", "probability", "tier", "alerting"]].to_string(index=False))
PY
```

### The two questions worth asking of any output

- Does the response say `data_mode: "replay"`? If that field ever goes missing,
  someone has wired live data in without wiring in the caveat.
- Does `horizon_hours` say `1`? If a slide claims a 3- or 6-hour forecast, the
  model behind it does not exist yet.

---

## 4. The live collectors — separate from all of the above

The collectors run on their own hourly schedule and are **not** connected to the
model. They exist to accumulate history that no one publishes.

```bash
# Health of the last run
cat data/live/_status.json

# How much history exists, and are we past the 24-hour cold start
PYTHONPATH=src python -c "
from bkkflood.collectors import coverage_report
print(coverage_report().to_string(index=False))"

# Look at the data
jupyter lab notebooks/10_live_collect.ipynb
```

`launchctl list | grep bkkflood` should show the scheduled job.

---

## 5. If something breaks

| Symptom | Cause |
|---|---|
| `ModuleNotFoundError: duckdb` | Wrong Python — `source .venv/bin/activate` first |
| API starts, every request 500s | `PYTHONPATH` not set to `"$PWD/src:$PWD"` |
| Dashboard loads but is empty | API not running on port 8000, or a `ts` outside 2019-01-01 → 2025-12-31 |
| Dashboard looks fine but nothing is alerting | Probably a dry timestamp — try `2025-11-13 03:00:00` |
| A collector row says `skipped` | Not a failure. It was polled less than ~48 min ago |
