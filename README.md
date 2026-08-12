# Bangkok Flood Forecast & Alerting System

Version 3.0 · Rebuilt from scratch, August 2026

A system that monitors road flooding in Bangkok from BMA's sensor network,
forecasts it 1, 3 and 6 hours ahead, and turns those forecasts into standard
CAP emergency messages — while being honest about how often it will be wrong.

**Start here:** [`BKK_Flood_Forecast_Master_Spec_v3.docx`](BKK_Flood_Forecast_Master_Spec_v3.docx)
(markdown source: [`docs/master_spec_v3.md`](docs/master_spec_v3.md)).
It is the build order for everything below. Section references in this README
point into it.

---

## The data in one table

Verified by a complete scan of all 28 raw CSVs on 7 August 2026 (spec §B).

| Dataset | Stations (2025) | Rows | Cadence | Years |
|---|---|---|---|---|
| Rainfall | 131 | 96,153,700 | 5 min | 2019–2025 |
| Canal water level | 300 | 198,730,656 | 5 min | 2019–2025 |
| Canal flow | 30 | 22,092,480 | 5 min | 2019–2025 |
| Road flood depth (**the target**) | 107 | 75,932,352 | 5 min | 2019–2025 |

Plus a 1 m DTM covering the whole city, district and sub-district boundaries,
and an inferred station registry (read its caveats in §B.8 before using it).

**The number that governs the model strategy: there are 837 flood events at the
15 cm tier in the entire seven-year archive.** Not per year — in total, across
all of Bangkok. That is why this project uses gradient-boosted trees plus onset
specialists rather than a Transformer (§E.6).

*(999 was the figure before the merge-gap and minimum-duration rules were
applied. Measured in `notebooks/02`: 1,469 raw excursions → 999 after the
persistence rule → 837 under the full definition. See
`docs/reports/phase0_verification.md`.)*

---

## Getting set up

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH="$PWD/src"
jupyter lab notebooks/
```

Then run the notebooks in order. Notebook 01 writes about 2 GB of Parquet and
takes roughly ten minutes; everything after it reads that instead of the CSVs.

---

## How the repository is laid out

```
config/config.yaml     THE single source of truth — every threshold, year,
                       split and exclusion. If a number appears twice in this
                       project, one of them is already wrong.

src/bkkflood/          Thin shared library. Only functions more than one
                       notebook needs: reading raw CSVs correctly, the flood
                       event definition, the quality scorecard, terrain maths.

tests/                 Fast unit tests on synthetic data — no data files, one
                       second to run. `pytest tests/ -v` before trusting any
                       number that came out of a 13.9 GB raster.

notebooks/             Where all data and ML work happens.
  00_data_inventory      what we hold, verified
  01_ingest_to_parquet   54.8 GB CSV → clean Parquet
  02_quality_and_events  quality scorecard + flood event detection
  03_terrain_from_dtm    1 m depression depth, slope, flow, TWI
  04_external_data       Open-Meteo forecast + ERA5, Traffy Fondue
  05_features            51 features, leakage checks, the GFS decision
  06_baselines           persistence / climatology / rain rule / always-negative
  07_train_lightgbm      general model — every row
  08_train_onset         onset specialist — dry roads only
  09_train_depth_quantiles  how deep, with a coverage check
  10_train_sequence      (Phase 6)
  11_evaluate            which comparisons are legitimate; lead-time distribution
  12_calibrate           do probabilities mean what they say; depth interval repair
  13_error_analysis      which floods are missed, and why

data/                  Raw archive (git-ignored), plus interim/ features/
                       external/ which the notebooks generate.
backend/               FastAPI service. Replay-only; every caveat is a
                       response field, not a footnote. See backend/README.md
frontend/              React + Vite + Leaflet dashboard. Districts as polygons,
                       caveats on screen rather than in a footnote.
db/                    PostgreSQL + PostGIS schema (Phase 9)
models/                Trained artefacts + metadata
docs/                  The spec, reports, and superseded v1/v2 documents
```

### Why there is a `src/` at all

The project convention is that analysis lives in notebooks. Three things cannot
be notebooks: the FastAPI service (a web server has to be importable), the React
frontend, and the handful of functions that 14 notebooks all need. Copying the
flood-event definition into 14 places is exactly how training and serving drift
apart, so it lives in `src/bkkflood/events.py` and everything imports it.

---

## Where the project is

| Phase | Work | Status |
|---|---|---|
| 0 | Config, ingestion, quality scorecard, event detection | **Done and verified** |
| 1 | Terrain from the 1 m DTM | **Done.** DTM wasn't bare earth in dense districts; fixed in Phase 1.5 (`terrain.ground_mask`). Bang Rak 4.54 → 1.25 m. Re-run `notebooks/03`. |
| 2 | External data (Open-Meteo, Traffy Fondue, ThaiWater) | **Done and verified.** ERA5 3,068,400 rows; GFS forecast rain 2,093,600 rows (2021–2025, 13 km); Traffy 199,968 reports. Guard passes. |
| 3 | Features and baselines | **Done.** 51 features × 7 years built. Baselines recorded: persistence gets **100% recall on already-flooded rows and 16% on dry ones** — see `docs/reports/phase3_findings.md`. GFS kept after measurement, but narrowly: 61% of a +0.0008 onset gain is real forecast skill, and it *degrades* overall discrimination — it should go to the onset specialist only. |
| 4 | LightGBM, onset specialists, depth quantiles | **Done — 72 models across 4 folds.** Onset specialist: 60% event POD vs persistence 36%, but only **1.1 points better than a rainfall threshold** on onset recall, **87% of its gain from the station's own depth history and 0.0% from terrain**, and a median lead of 15 min everywhere. Depth intervals FAIL coverage (43–63% on wet rows vs 90% target). See `docs/reports/phase4_findings.md`. |
| 5 | Honest evaluation | **Done — notebooks 11–13.** Main finding: **when a district floods, only 35% of its stations do** — and every rain/terrain/canal feature is identical across them. The ceiling is spatial resolution, not model capacity. Also: the Phase 4 'decay' was a base-rate artefact; depth intervals need a two-stage model; **6.6 call-outs per flood warned**. See `docs/reports/phase5_findings.md`. |
| 6 | Sequence-model challenger | |
| 7 | FastAPI backend | **Done.** `backend/app/main.py` + `src/bkkflood/serving.py`. Serves **replay, not live data** — every response carries `data_mode`. Depth is never served; `cap_status` is `Test`, test-guarded. See `backend/README.md`. |
| 8 | React frontend | **Done.** Vite + React + Leaflet + Recharts. District polygons (never pins), non-dismissible replay banner, no predicted depth anywhere. Opens on a real flood event. See `frontend/README.md`. |
| 9 | PostGIS + deployment | |
| 10 | CAP generation + BMA pack | |

---

## Rules this project does not bend

1. **Chronological splits only.** Neighbouring 5-minute rows are near-identical;
   a random split inflates scores by 20–30 points and is indefensible.
2. **Baselines first.** Persistence and climatology are recorded before any
   model is trained, so every later number has a bar next to it.
3. **Recall is reported twice** — overall, and on *onset* rows only (where the
   road was dry). A single recall number describes a monitor, not a forecaster.
4. **Event POD is never quoted without median lead time beside it.**
5. **`cap_status` stays `Test`** until BMA authorises in writing. It is
   config-gated and requires a deliberate change.
6. **Every caveat is a field in the API response**, not a footnote in a
   document. A caveat that lives only in a PDF may as well not exist.
7. **A forecast feature may only contain what was knowable beforehand — and
   that is checked by value, not by filename.** Open-Meteo's ERA5 archive is
   what actually fell; its historical-forecast archive is what was predicted.
   Without an explicit `models=` the forecast endpoint quietly serves the
   reanalysis, which once passed every naming convention this project has while
   being the answer sheet. Call
   `assert_forecast_is_not_reanalysis()` before using `rain_fcst_*`.
8. **Ask before scraping a government system.** `pumps.bangkok.go.th` is exactly
   the data this project needs and no collector was written for it on purpose.
9. **Terrain is computed at 1 m and never coarsened for local features.** Urban
   water collects in dips a few metres across; the 31 m SRTM test in earlier
   versions could not have found them, and its null result said nothing about
   terrain. See `notebooks/03`.
10. **Every recall figure is reported twice — overall and on onset rows.** The
   baselines make the reason concrete: persistence scores 100% on rows where the
   road was already flooded and 16% where it was dry. One averaged number
   describes a sensor readout.
11. **A feature must be available at serving time, or it is not a feature.**
   `era5_*` is reanalysis published ~5 days late. It was worth a fifth of the
   onset model's PR-AUC and is excluded from every model, because a column that
   is populated in training and NaN in production makes the offline score a
   fiction. Guarded by a test.
12. **Raw PR-AUC is never compared across years.** Its floor is the base rate,
   and 2024 had a fifth the floods of 2022. Quote lift over base rate, or event
   POD. Reading PR-AUC across years once produced a false "the model is
   degrading" conclusion that nearly blocked the project.
13. **A per-station feature requires a real station coordinate.** Every
   coordinate we hold is a district centroid — all sensors in a district share
   one point. `terrain.sample_points()` refuses to run on them rather than
   returning a number that looks per-station and is not.

---

## Reproducing the numbers

Every figure in Part B of the spec is regenerated by notebooks 00–02 and
written to `docs/reports/`. `docs/reports/phase0_verification.md` records the
comparison between what the notebooks produce and what the spec claims.
