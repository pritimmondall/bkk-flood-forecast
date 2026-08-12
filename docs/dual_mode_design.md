# Running replay and live side by side — design

> ## START HERE — for a fresh session
>
> **Paste this to begin:**
>
> > Read `docs/dual_mode_design.md`. Do **Job 0**, then **Job 1**, then **Job 2**.
>
> ### Job 0 — commit everything to git (5 minutes, do this first)
>
> The last commit is 5 August 2026 and belongs to the **deleted v2 project**.
> Roughly 160 files — every phase of v3, the models, the API, the dashboard,
> the reports — have never been committed. One disk failure loses all of it.
>
> ```bash
> rm -f .git/index.lock          # left over from an interrupted command
> git add -A
> git commit -m "v3.0: phases 0-5, 7, 8 - features, models, evaluation, API, dashboard"
> ```
>
> ### Job 1 — save all 9 models (about 1 hour, no new modelling)
>
> Only **two** models are on disk (`models/*.txt`), both 15 cm / 1 hour. The
> other 70 trained in Phase 4 were measured and discarded, so the dashboard can
> only answer *"will it flood within 1 hour"* — not 3 h or 6 h.
>
> In `notebooks/07_train_lightgbm.ipynb` and `notebooks/08_train_onset.ipynb`,
> the fold loop calls `run_fold(...)` without `save_as=`. Add it, so each of the
> 3 tiers × 3 horizons is written for the **most recent fold** (train 2019–2023,
> test 2025):
>
> ```python
> run_fold(FOLDS[-1], tier, h, "onset", con=con,
>          save_as=f"onset_t{tier}_h{h}_final")
> ```
>
> Then update `serving.py` so `/api/forecast` accepts `tier` and `horizon`
> parameters and loads the matching bundle. `load_bundle()` is already keyed by
> name and cached, so this is mostly routing.
>
> **Result:** the dashboard can show 1 h / 3 h / 6 h risk at 5, 15 and 30 cm.
>
> Quote the right number for each: event POD is **not** comparable across
> horizons (see `phase4_findings.md` §2a — the alert window widens with the
> horizon, which inflates it).
>
> ### Job 2 — build the live collector (this document, sections below)
>
> Start with `thaiwater.py`. It has standalone value: ThaiWater publishes
> **current values only**, so every day the collector does not run is real data
> at real coordinates lost permanently.
>
> ### Before promising anything about live mode
>
> Read `docs/reports/live_forecasting_feasibility.md`. The measured numbers:
> replay **53%** event POD, live-on-public-data **4.9%**. The gap is BMA's rain
> gauge feed, and no public source substitutes for it. Live mode is worth
> building to accumulate history and prove the integration — **not** as the
> working system.


Written 10 August 2026. Not yet built. This is the specification for whoever
picks it up next, including a future session of this work.

---

## The decision

Keep **both** modes. They answer different questions and neither replaces the
other.

| | `replay` | `live_public` |
|---|---|---|
| Data | 7 years of BMA archive (2019–2025) | ThaiWater + Open-Meteo + BMA pumps |
| **Event POD** | **53%** | **4.9%** |
| Precision | 16% | ~2% |
| Purpose | the demonstration that the method works | proving integration, and accumulating history |
| Honest description | "what the system would have said" | "an early prototype on partial data" |

Both numbers are measured (`live_forecasting_feasibility.md`, sets A and E).

---

## Why live mode is worth building despite scoring 5%

**It accumulates history that does not otherwise exist.** ThaiWater and
`pumps.bangkok.go.th` publish current values only — there is no downloadable
past. Every day the collector does not run is a day of real observations at real
coordinates that is gone permanently. By next monsoon a collector started now
would hold a full season.

**It is the switch that makes the BMA feed instant.** The day a rain gauge feed
opens, one config change takes the same pipeline from 5% to roughly 45%. Nothing
is rebuilt.

**It gives us coordinates.** ThaiWater returns `tele_station_lat/long` — genuine
positions. Phase 5 established that district-average terrain contributes 0% of
model gain precisely because we have no coordinates. This is the first real
positional data the project has held.

---

## The rule that makes running both honest

**Every mode carries its own measured performance in every response.** Not in a
document, not in a README — in the JSON, next to the predictions.

```json
{
  "data_mode": "live_public",
  "mode_performance": {
    "event_pod": 0.049,
    "precision": 0.02,
    "measured_on": "test year 2025, 15 cm / 1 h",
    "plain_english": "Catches about 1 flood in 20. Not suitable for dispatch."
  },
  "sources": ["thaiwater", "open-meteo-gfs", "bma-pumps"],
  "missing_sources": ["bma-rain-gauges", "bma-road-sensors"],
  ...
}
```

A user switching modes must see the number change. If the dashboard looks the
same in both modes, the design has failed.

---

## What to build

### 1. `src/bkkflood/collectors/` — one module per source

Each exposes `fetch() -> DataFrame` and writes append-only Parquet under
`data/live/<source>/<date>.parquet`. Append-only matters: this is the historical
record being created, and it must never be rewritten.

| Module | Endpoint | Cadence | Notes |
|---|---|---|---|
| `thaiwater.py` | `api-v3.thaiwater.net/api/v1/thaiwater30/provinces/waterlevel?province_code=10` | hourly | 11 Bangkok canal stations, no auth, real coordinates |
| `openmeteo.py` | already implemented in `external.py` | hourly | reuse, do not rewrite |
| `bma_pumps.py` | `pumps.bangkok.go.th` | 5 min | **ask permission first** (project rule 8) |

### 2. `src/bkkflood/live.py` — feature assembly

Builds the same feature contract as `features.py` from live sources, leaving
unavailable columns as NaN. LightGBM handles NaN natively, so the same booster
serves both modes; only the inputs differ.

**Do not impute missing sources.** An invented rain gauge reading is worse than
a NaN, because the model cannot tell it is missing.

### 3. `serving.py` — a `mode` parameter

`forecast_at(ts, mode="replay" | "live_public")`. The model, threshold and
downsampling correction are unchanged. Only the feature source and the
`mode_performance` block differ.

### 4. Frontend — a mode toggle with the numbers attached

The banner text and the performance figures change with the mode. The live mode
banner must state "catches about 1 flood in 20" in those words.

---

## Cold start

Features such as `fl_max_24h` and `rain_rf24hr_mean` look back 24 hours. Until
the collector has run a full day, live mode must report
`"cold_start": true` and refuse to emit alerts. A confident zero from a system
with no history is the worst possible output.

---

## The order to build it in

1. **`thaiwater.py` collector, scheduled hourly.** Start today — the history
   clock starts when it does, and nothing else depends on it.
2. Ask BMA about the pump feed. One email, and it fixes the pump blind spot
   identified in Phase 5.
3. `live.py` feature assembly, with NaN for everything absent.
4. `mode` parameter through `serving.py` and the API.
5. Frontend toggle.

Step 1 has value on its own even if steps 2–5 never happen.

---

## What must not happen

**Live mode must never be presented as the working system.** At 5% detection it
would strand people who trusted it. In any demonstration to BMA, replay is the
system and live is the integration proof.

**`cap_status` stays `Test` in both modes.** Unchanged by any of this.
