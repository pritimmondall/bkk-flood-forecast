# Bangkok Flood Forecast — Full Project Roadmap

*Master synthesis, 2026-07-15. Sources: project brief, `data/` (verified), `BKK_Flood_Forecast_Technical_Roadmap_1.docx`, `BKK_FF_Dashboard Scheme.docx`, `CAP Standard.pdf`, Phrae reference deck. Detail on the ML portion and the supervisor docs lives in `docs/ml_engineering_project_analysis.md` and `docs/supervisor_reference_docs_review.md` — this document is the top-level plan that ties all of it together.*

## 1. Verdict

Everything needed to ship a working, honestly-evaluated MVP in the 15–20 day sprint is already on hand. Nothing needed for that MVP is missing. What's missing (station coordinates, canal/drainage network, per-station threshold calibration, live weather) blocks the *full* vision in the original project brief, not the sprint deliverable — and the team's own roadmap already scopes that correctly as phased future work. The job now is execution discipline, not data acquisition.

## 2. Full feature list — where each one comes from and who owns it

| Project brief feature | Specified in | Owner | Sprint status |
|---|---|---|---|
| Interactive Bangkok Map | Dashboard Scheme panel 2 | Dashboard engineer | Station markers only (no interpolation) |
| Flood Forecast | Dashboard Scheme panels 3, 4, 10 | ML engineer (you) → Dashboard | Core deliverable |
| Water Level Monitoring | Dashboard Scheme panel 6 | Data/GIS → Dashboard | In scope |
| Rainfall Monitoring | Dashboard Scheme panel 1 | Data/GIS | In scope (rf5min…rf24hr already computed) |
| Flow Monitoring | Dashboard Scheme panels 1, 6 | Data/GIS | In scope, `FW.PKG.01` fault needs a decision first |
| Flood Risk Dashboard | Dashboard Scheme panels 1, 3, 4 | All three | Core deliverable |
| Historical Trends | Implied by panel 6, not fully specified | Dashboard | Needs a lightweight spec — see §6 |
| CAP Alerts | Dashboard Scheme + CAP Standard.pdf | Dashboard engineer | Mapping + one sample message only |
| Flood Hotspots | Dashboard Scheme panel 9 | All three | Rule-based (thresholds), not ML-driven interpolation |
| Forecast Charts | Dashboard Scheme panels 4, 10 | ML engineer (you) | Core deliverable |

## 3. System architecture — unchanged core, sharpened contract

The five-layer architecture from the team roadmap (data → PostGIS → model → predictions/alerts → dashboard) stays as-is. What's new from the supervisor docs is the **output contract** between the model layer and everything downstream — this is the API surface your model needs to actually produce:

For each station (and each area aggregation, once station coordinates exist):
- Per horizon (1h / 3h / 6h): event-probability (risk %) and depth quantiles (P05/P25/P50/P75/P95).
- Derived KPI fields the dashboard reads directly, not recomputes: Peak Risk (%), Peak Time, Time to Warning; Peak Depth (cm), Peak Time, Time to 15cm, Time to 30cm.
- Area aggregation rule: **P95 across stations in the selected area is the primary displayed line**; area-weighted mean is secondary.

Everything else (FastAPI serving a versioned checkpoint, PostGIS as the single source of truth per data type, React/Leaflet reading only from the API) is confirmed and doesn't need to change.

## 4. Phased roadmap

**Phase 0 — Foundation (now → Day 4).** Clean all years to one schema (null coercion, per-year truncation check, CRLF-safe parsing). Build the station registry (approximate geocoding from Thai names, swappable later). Confirm the flood-label definition holds across all years, not just 2025. Scaffold FastAPI + React/Leaflet against dummy data so the skeleton is wired end-to-end early. Decide the `FW.PKG.01` and `wl_out01`/`wl_out02` handling now, not mid-training.

**Phase 1 — Working pipeline, real model (Days 5–9).** Lag/rolling features for water and flow. Chronological split with a verified monsoon-season test window. Baseline ladder: persistence → LightGBM → GRU (Darts, direct multi-horizon, dual-head). Real FastAPI endpoints off PostGIS; station markers on the map. First evaluation pass against the 12 points.

**Phase 2 — Feature-complete MVP (Days 10–14).** Per-station/per-tier evaluation depth; FP/FN spatial mapping. TFT only if ahead of schedule. Forecast charts with the P95-primary / weighted-mean-secondary rule and the exact KPI chips from §3. CAP mapping (urgency by horizon bucket — §5.4) + one valid sample alert. Hotspot panel via threshold rules, not interpolation. Historical trends view (see §6).

**Phase 3 — Integration (Days 15–20).** Everyone against real data end-to-end. BMA one-pager. Rehearsed demo. This document plus the two supporting docs serve as the technical roadmap deliverable (evaluator point #12).

**Phase 4 — Post-sprint, not this cycle.** Canal/drainage integration (check the Open Bangkok / DDS lead before assuming it's blocked — see the ML analysis doc), IDW/Kriging flood-surface interpolation once coordinates + canal data exist, per-station threshold calibration (see §5.3), GNN modeling once canal topology exists, live weather integration (Open-Meteo now, TMD/ThaiWater for BMA-facing later), full CAP operational dispatch to BMA's actual alerting channel.

## 5. Strategy by component

**5.1 Data.** One cleaning script, run identically per year/dataset. Coerce `"NULL"` strings to real nulls at ingestion, not downstream. Treat Flow's all-4-column nulls as a masked timestep, not per-column imputation. Re-export any future BMA pulls as CSV/Parquet — the row-limit truncation is an Excel artifact, not a data problem, and doesn't recur once you stop round-tripping through `.xlsx`.

**5.2 Modeling (your portion — full depth in `docs/ml_engineering_project_analysis.md`).** Ladder, don't leap: every added layer of complexity earns its place with a measured gain over the previous one. Dual-head (classification + quantile regression) on one shared encoder. Direct multi-horizon output, not recursive. Evaluate per-station and per-tier; report PR-AUC and F2 alongside F1, since aggregate accuracy is meaningless against a 0.08%-positive label.

**5.3 GIS / dashboard.** Station registry now with approximate coordinates; don't block feature engineering on exact ones. Keep the universal 5/15/30cm threshold for this sprint — 300 water stations don't have enough individual history yet for reliable per-station calibration, and it's what the CAP mapping and evaluator both assume. Flag per-station percentile calibration (the Phrae reference system's approach) as the concrete phase-2 upgrade once each station has 2+ clean years.

**5.4 CAP alerting.** `status` stays `Test`/`Exercise` throughout — never `Actual` in a prototype. Urgency maps directly off which forecast horizon triggers the alert: a 1h-ahead threshold crossing → `Immediate` (CAP's own definition is <1hr); 3h/6h-ahead crossings → `Expected` (1–12hr). `severity` from the depth tier, `certainty` from `Observed` (sensor-confirmed, for the observed panel) vs `Likely` (forecast-only, P95 crosses threshold).

**5.5 Backend/infra.** Training offline as a batch job; FastAPI only ever loads a versioned checkpoint. New GIS data becomes a new PostGIS table, never a pipeline rewrite — this is what makes the "add data later without redesigning" requirement in the original brief actually true. No Docker/CI needed for a 15–20 day demo; skip it.

## 6. One gap the source docs don't fully resolve: Historical Trends

The project brief lists "Historical Trends" as a required feature, but none of the three reference docs spec it as its own panel — it's implied inside the Water Levels panel. Recommend treating it as a simple, low-cost addition: a time-range-selectable chart (station or area level) over the cleaned historical data you already have, reusing the same chart component as the forecast charts but plotting observed rather than predicted values. This doesn't need new data or new modeling work, just a second read path against data already in PostGIS — worth confirming scope with your supervisor so it doesn't get built as something more elaborate than intended.

## 7. Limitations and solutions

| # | Limitation | Impact if unaddressed | Solution | When |
|---|---|---|---|---|
| 1 | No station coordinates | Map can't plot real positions, no spatial joins | Approximate geocode from Thai station names now; swap for official coordinates when BMA provides them | Phase 0 |
| 2 | No canal/drainage network | No hydraulic routing, no GNN, no lead-time propagation between stations | Document as future work; check the Open Bangkok / DDS open-data lead before assuming it's fully blocked | Phase 4 (or sooner if the lead pans out) |
| 3 | No dedicated road-elevation layer | Can't independently recompute `Flood Depth = Water Level − Road Elevation` for the observed panel | Use the existing `flood` column directly as ground truth (it already is this computed depth); extract road elevation from `DTM_1M` only if the observed panel needs to compute it live | Phase 2 if needed |
| 4 | Severe class imbalance (89% zero, 0.08% real nonzero) | Naive accuracy hides a model that never predicts a real flood | Aggregate years, class-weight or focal-loss the classification head, report PR-AUC/F2/per-tier metrics instead of accuracy | Phase 1 |
| 5 | `FW.PKG.01` extreme negative flow values (to −3,285 m³/s) | Distorts feature scaling/normalization if left in | Clip, exclude, or flag as a sensor fault — decide with the Data/GIS engineer before training | Phase 0 |
| 6 | `wl_out01`/`wl_out02` mostly (not universally) null | Blanket exclusion per the original roadmap would drop usable stations | Per-station null-rate check, include where populated | Phase 0 |
| 7 | Row-limit truncation unverified outside Flood 2025 | Silent data loss in other files/years if truncation is still present | Re-run the truncation check per dataset/year before trusting completeness | Phase 0 |
| 8 | Universal depth thresholds vs. the Phrae example's per-station calibration | Alerts may under- or over-trigger for atypical stations | Keep universal thresholds for the sprint; per-station percentile calibration as phase-2 | Phase 4 |
| 9 | No live weather feed | Can't do true real-time nowcasting, only backtesting | Open-Meteo for prototyping now; ThaiWater.net API (see reference lead) or TMD for BMA-facing later | Phase 4 |
| 10 | Generic dashboard mockup images misread as spec | Risk of building UI/features around placeholder data (Soil Moisture Index, Evapotranspiration aren't in any dataset) | Confirmed with supervisor (2026-07-15): Phrae pptx is a UI reference only, docx's 3 screenshots are illustrative — ignore both as literal spec | Resolved |
| 11 | Small team (3 people), 15–20 days, new to applied AI/GIS | Scope creep back into cut items (GNN, full interpolation, live weather) | Hold the "Scope: What's In, What's Cut" line from the team roadmap; revisit that section, not memory, on any "should we also add..." | Ongoing |
| 12 | Full CAP operational dispatch is out of scope | Can't actually push alerts to BMA's real alerting channel this sprint | Build the mapping logic + one valid sample message only; document full dispatch as future integration work | Resolved (by design) |
| 13 | "Historical Trends" underspecified | Risk of over- or under-building this feature | Treat as a second read path over existing cleaned data reusing the forecast chart component; confirm scope with supervisor | Phase 2 |
| 14 | Spatial interpolation (IDW/Kriging) expensive to validate | Hotspot panel can't show a smooth flood surface this sprint | Colored station markers substitute for the demo; interpolation is phase-4 | Phase 4 |

## 8. Immediate next actions

- Data/GIS engineer: resolve `FW.PKG.01` and `wl_out01`/`02` handling; check the Open Bangkok/DDS canal lead and the ThaiWater.net API before treating either as fully blocked.
- ML engineer (you): re-verify truncation across all files/years; start Phase 1 feature engineering without waiting on coordinates.
- Dashboard engineer: scaffold the FastAPI/React skeleton against dummy data now, using the output contract in §3 so the real model can drop in later without an interface rewrite.
