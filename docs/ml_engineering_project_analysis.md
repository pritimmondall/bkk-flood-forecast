# BKK Flood Forecast — Project Analysis & ML Engineering Deep Dive

*Prepared 2026-07-14. Cross-checked against the live `data/` folder and `BKK_Flood_Forecast_Technical_Roadmap_1.docx`.*

## 1. Bottom line: is the data enough?

**For the core ML forecasting job (your portion): yes, mostly.** Rain, Water, Flow, and Flood, 2019–2026, 5-minute cadence, are enough to build and honestly evaluate a forecasting model at 1h/3h/6h horizons. That's the hard part of the evaluator's 12 points (#1–#8) and it's answerable with what's already on disk.

**For the full vision in the project brief: no.** The interactive GIS dashboard, flood hotspot mapping, and canal-aware modeling need station coordinates, canal network, and drainage network — none of which exist yet. The roadmap already scopes this correctly: build the forecasting model now, treat GIS enrichment as an incremental, separate track. I'd only add one correction below (the roadmap's data-quality numbers are stale) and one lead (Bangkok's canal/drainage data may already be publicly obtainable, worth checking before writing it off as blocked-on-BMA).

## 2. Data inventory — current, verified state

This corrects Section 6 of the roadmap, which was computed against a much smaller export (10 stations/file) than what's actually in `data/` now.

| Dataset | Years | Stations (2025) | Cadence | Size | Verified condition |
|---|---|---|---|---|---|
| Flood (label) | 2019–2025 | 107 | 5-min | — | 89.22% = 0, 10.70% literal `"NULL"` string, 0.081% real nonzero. Max 61.5cm. No row-limit truncation in 2025 (all sites have the full 105,120 rows). |
| Flow | 2019–2025 | 30 | 5-min | — | 15.93% of rows have all 4 columns null together (sensor downtime, not scattered noise — mask the timestep). 41,581 negative-flow rows; 14,809 of those are below −1,000 m³/s, **all from one station, `FW.PKG.01`** — this is new, not in the roadmap, and doesn't look like plausible tidal backflow. |
| Rain | 2019–2025 | 131 | 5-min | — | rf5min…rf24hr rolling windows pre-computed. Filenames inconsistent (`2019.csv` vs `Rain 2021.csv`). |
| Water | 2019–2025 | 300 | 5-min | ~28GB | `wl_out01`/`wl_out02` are 84.16% / 99.67% NULL — not universally empty, so don't blanket-exclude per the roadmap; decide per-station. |
| Total | | | | ~52GB | UTF-8 BOM on every header; missing values are the literal string `"NULL"`, not blank cells; CRLF line endings. |

Not yet re-checked: whether the row-limit truncation is actually absent from Flow/Rain/Water 2025 and from years other than 2025 — Flood 2025 was the only file confirmed clean so far.

Also on hand: Bangkok admin boundary (GeoJSON/shapefile), a 1m DTM, and SRTM-derived rasters (slope, aspect, hillshade). Not yet: station coordinates/metadata, canal network, drainage network.

## 3. What's missing, and how much it actually matters

| Missing item | Blocks | Severity |
|---|---|---|
| Station coordinates/metadata | Map plotting, nearest-station joins, spatial interpolation, CAP `area.polygon` per station | High for the dashboard, **not** a blocker for the forecasting model itself (per-station time-series models don't need coordinates to train) |
| Canal network | Hydraulically realistic flow routing, GNN modeling | Low for this sprint — correctly cut to future work |
| Drainage network | Same as above, plus pump/gate-aware forecasting | Low for this sprint |
| High-confidence DEM tied to stations | Flood-surface interpolation (IDW/Kriging) | Low for this sprint — station markers substitute fine for a demo |
| Live weather feed | Real-time (not just backtested) forecasting | Not needed yet — backtesting uses historical rain as its own "future" |

One addition worth flagging: BMA's "Open Bangkok" open-data initiative and a Department of Drainage and Sewerage flood-risk platform reportedly already publish canal/drainage layers (~1,980 canals, ~2,745 km). If real, that could pull "canal network" out of the blocked-on-BMA column much sooner than the roadmap assumes — worth ten minutes for the Data/GIS engineer to check before treating it as a hard blocker. I haven't verified this dataset's completeness or license myself, so treat it as a lead, not a confirmed source.

## 4. Project steps, end to end

The roadmap's 4-block sprint structure is sound; here's the same shape with current status folded in.

**Phase 1 — Pipeline foundation** (Data/GIS lead, ML depends on it)
Clean all years to a consistent schema; coerce `"NULL"` strings to real nulls; confirm truncation status per dataset/year, not just Flood 2025; re-export future pulls as CSV/Parquet. Build a station registry (code → name → approximate coordinates via geocoding, swappable for official coordinates later).

**Phase 2 — Modeling** (your lane)
Confirm the flood-label definition across all years; engineer lag/rolling features for water and flow (rain's already computed); chronological train/test split with a monsoon-season check; baseline ladder from persistence through LightGBM to GRU (Darts), TFT if time allows; full evaluation against the 12 points.

**Phase 3 — Dashboard & alerts** (Dashboard lead, consumes your model's output)
FastAPI endpoints off PostGIS; React/Leaflet map with station markers; forecast charts with uncertainty bands; CAP alert mapping + one sample message; hotspot panel.

**Phase 4 — Integration**
Wire all three together against real data; bug fixes; BMA one-pager; rehearsed demo.

**Beyond this sprint**: canal/drainage integration, IDW/Kriging surfaces once coordinates exist, GNN modeling once canal topology exists, live weather API, full CAP operational dispatch.

## 5. Each component, briefly

- **FastAPI backend**: serves predictions from a versioned model checkpoint; training stays offline and decoupled from serving.
- **PostgreSQL + PostGIS**: one table per data type (readings, station registry, each GIS layer) — new data becomes a new table, not a pipeline rewrite.
- **React + Leaflet dashboard**: the map, forecast charts, monitoring panels, hotspot view — all read from the API, nothing computed client-side.
- **CAP alert generator**: maps your model's 4-tier depth classification onto CAP's `severity`/`urgency`/`certainty` fields; status stays `Test`/`Exercise` throughout the sprint, never `Actual`.
- **Forecasting model (your portion)**: turns cleaned time-series into depth + risk-tier predictions at 1h/3h/6h. Everything downstream depends on this being honestly evaluated, not just accurate-looking.

## 6. Your portion — ML engineering, in depth

**Scope**: feature engineering, the baseline ladder, the deep models, and the full evaluation story (evaluator points #1–#8).

**Current status**: `notebooks/eda_flood_forecast.ipynb` is scaffolded (file/schema audit, completeness check, label distribution, roadmap cross-check, a label-definition sync checklist) but not executed — by design, since it's meant to run in your own local/Colab environment against the full ~52GB, not in a sandbox.

**Label definition** (evaluator point #5 — already resolved, don't relitigate it): flood is a continuous depth in cm. Derive two targets from it — a regression target (depth) and a classification target thresholded at the dashboard's own tiers (Normal <5cm, Watch 5–15cm, Warning 15–30cm, Critical >30cm).

**Feature engineering**: rain's rolling windows (rf5min…rf24hr) are ready to use as-is. Build equivalent lag/rolling features for water level and flow. Join to station identity now (station code as a categorical/embedding), join to physical location once coordinates land — don't block feature work on the Data/GIS engineer.

**Model ladder** — earn complexity, don't assume it:
1. Persistence/climatology floor.
2. LightGBM on lag features — fast signal on whether sequence modeling is worth the cost at all.
3. GRU (global model, per-station embedding) via Darts — the sprint's real target.
4. TFT — stretch goal.

On the GRU-vs-TFT choice specifically: published comparisons on rainfall-runoff tasks find GRU competitive and cheaper for short-horizon forecasts, while TFT's attention mechanism and native multi-horizon output tend to help more as the horizon lengthens and when you want built-in interpretability. Given the evaluator explicitly wants three horizons (1h/3h/6h) and both a classification and quantile-regression head, TFT is a structurally better fit for that exact ask than a GRU with heads bolted on — but GRU is the safer bet to guarantee something trained and evaluated inside the sprint. The roadmap's call to keep GRU as the committed target and TFT as upside-only, time-permitting, is the right call; I'd just make sure the GRU build reserves the multi-horizon direct-output structure (not recursive) from the start, since retrofitting that later costs more than building it in.

**Dual-head design**: one encoder, two heads — a classification head (event probability per tier) and a quantile-regression head (P05/P25/P50/P75/P95 depth), the latter also producing the uncertainty band the dashboard's forecast charts need.

**Evaluation** — this is where most of the evaluator's points live:
- Report precision/recall/F1/FNR **per station and per severity tier**, not one aggregate number — aggregate accuracy is meaningless when 89% of the label is a single class.
- Add PR-AUC and an F2 score (recall weighted above precision) alongside F1: missing a real flood event is more costly than a false alarm, and F2 reflects that asymmetry directly.
- Confusion matrix per station/tier, and map false negatives spatially once coordinates exist (point #8).
- Chronological split only, and explicitly confirm the held-out window contains real monsoon events — a clean split that happens to test on a dry season proves nothing.
- Data inventory table (point #9) — years × resolution × station count × missing-rate per file; the corrected numbers in Section 2 above are the current version of that table.

**Concrete blockers to resolve before training, not during**:
- `FW.PKG.01`'s extreme negative flow values (down to −3,285 m³/s) — decide clip vs. exclude vs. flag-as-sensor-fault with the Data/GIS engineer before it distorts feature scaling.
- `wl_out01`/`wl_out02` — 84%/99.7% null, not 100% — worth a per-station inclusion decision rather than a blanket drop.
- Confirm truncation status for Flow/Rain/Water 2025 and for years other than 2025 before assuming the dataset is uniformly clean.

## 7. My overall take

The datasets you have are enough to do real, defensible ML work — the imbalance and gaps are the normal shape of hydrological sensor data, not a reason to wait for more data. The bigger risk to the project isn't data volume, it's two things: (1) evaluating on an aggregate metric that hides the fact that the model rarely sees a real flood, and (2) letting the "future work" items (canal network, GNN, live weather) creep back into sprint scope — the roadmap already guards against both, and I'd hold that line.

If I had to bet where the sprint gets tight, it's Phase 2 evaluation depth (per-station/per-tier breakdowns take longer than they look) and Phase 1 station geocoding accuracy (approximate geocoding from Thai names is a real source of downstream map error). Neither is a data-sufficiency problem — both are execution-time problems, which is the right kind of problem to have this early.

## Sources consulted

- [Temporal Fusion Transformers for Streamflow Prediction (arXiv)](https://arxiv.org/pdf/2305.12335)
- [Efficacy of Temporal Fusion Transformers for Runoff Simulation (arXiv)](https://arxiv.org/pdf/2506.20831)
- [Flood Forecasting Using Hybrid LSTM and GRU Models (MDPI)](https://www.mdpi.com/2073-4441/15/22/3982)
- [OASIS CAP v1.2 Standard](https://docs.oasis-open.org/emergency/cap/v1.2/CAP-v1.2-os.html)
- [Machine Learning for Generalizable Prediction of Flood Susceptibility (arXiv)](https://arxiv.org/pdf/1910.06521)
- [Bangkok Metropolitan Administration's Flood Risk Management Platform — CivicDataLab](https://civicdatalab.in/work/climateaction/bma-flood-risk-data-platform/)
