# Pre-Modeling Dataset Research Report

*2026-07-16. All numbers below were verified this session by full scans of the raw CSVs in `data/` (not sampled, not carried over from the old roadmap). This supersedes the per-2025-only numbers in earlier docs.*

---

## 1. What the model will do

**One sentence:** given the last N hours of rain, water-level, and flow readings across the BMA sensor network, predict for each flood station whether a road flood will occur in the next 1h / 3h / 6h, and how deep it will be.

**Architecture: dual-head, direct multi-horizon** (per `docs/full_project_roadmap.md` §3, §5.2):

| Head | Output per station, per horizon (1h/3h/6h) | Used for |
|---|---|---|
| Classification | P(flood ≥ threshold) — risk % | Alerts, CAP, risk map |
| Quantile regression | Depth quantiles P05/P25/P50/P75/P95 | Forecast charts, KPI chips (Peak Depth, Time to 15cm/30cm) |

- Direct multi-horizon (3 output slots), not recursive.
- Model ladder: persistence baseline → LightGBM → GRU (Darts) → TFT only if ahead of schedule.
- Dashboard reads Peak Risk/Peak Time/Time-to-Warning per station and P95-across-stations for area aggregation — the model must emit these, not have the dashboard recompute them.

**Prediction unit:** (flood station, timestamp) → next-1h/3h/6h outcome. Trained on 2019–2024, tested on a chronological monsoon-season window (details in §7).

## 2. Datasets required

| # | Dataset | Role | Status |
|---|---|---|---|
| 1 | `Flood_2019-2025/` | **Label source** (road flood depth, cm) + autoregressive feature | On hand, 8.1GB |
| 2 | `Rain_2019-2025/` | Primary driver features (pre-aggregated rainfall accumulations) | On hand, 13GB |
| 3 | `Water_2019-2025/` | Canal water-level features (leading indicator) | On hand, 28GB |
| 4 | `Flow_2019-2025/` | Drainage/flow features (secondary) | On hand, 2.9GB |
| 5 | Station registry (code → name → coordinates) | Joins the 4 networks spatially; map plotting | **Missing — must build** (approximate geocoding, Phase 0) |
| 6 | `DTM_1M/` + SRTM derivatives | Static terrain features (elevation, slope) per station | On hand, 18GB — usable only after #5 exists |
| 7 | `tha_admin_boundaries.gdb/.shp` | District aggregation for the dashboard | On hand |
| 8 | Live weather / forecast rain (Open-Meteo, ThaiWater API) | True forecasting instead of nowcasting from observed rain | Phase 4, not this sprint |

No dataset needed for the sprint MVP is missing except the station registry, which is buildable.

---

## 3. Dataset 1 — Flood (`Flood_2019-2025/`) — the label

### 3.1 What it holds
`flood_code, flood_name, site_timestamp, flood` — road flood depth in **cm** at 5-min cadence, one CSV per year. Station names are Thai road/location descriptions. This column *is* `Water Level − Road Elevation` already computed by BMA; it is the ground truth, no recomputation needed.

Verified inventory (full scans, 2026-07-16):

| Year | Stations | Rows | NULL % | Nonzero % | ≥5cm | ≥15cm | ≥30cm | Max (cm) |
|---|---|---|---|---|---|---|---|---|
| 2019 | 99 | 10,406,880 | 0.00 | 1.363 | 8,386 | 2,593 | 1,209 | 148.8 |
| 2020 | 99 | 10,435,392 | 0.03 | 2.964 | 8,517 | 2,284 | 354 | 73.3 |
| 2021 | 102 | 10,593,504 | 1.89 | 1.429 | 7,772 | 1,890 | 345 | 139.4 |
| 2022 | 102 | 10,722,240 | 2.92 | 0.223 | 13,647 | 4,763 | 822 | 51.4 |
| 2023 | 107 | 11,247,840 | 10.11 | 0.099 | 4,903 | 1,490 | 271 | 49.2 |
| 2024 | 107 | 11,278,656 | 8.20 | 0.096 | 2,681 | 449 | 59 | 50.0 |
| 2025 | 107 | 11,247,840 | 10.70 | 0.081 | 5,023 | 1,555 | 202 | 61.5 |

Row counts = stations × 105,120 exactly, every year. Every file ends 2025-12-31 23:55 (or its year's equivalent). **The Excel row-truncation issue does not exist in any year** — fully resolved. The 2019 station set is a strict subset of 2025's (stations only get added, never removed).

### 3.2 Is it perfect? No — the problems
1. **"Nonzero" ≠ flood.** The 1.4–3.0% nonzero rates in 2019–2021 are dominated by sub-5cm sensor noise/standing water. Example: `FL.LSI.03` in 2021 has 21,754 nonzero readings with mean 0.3cm, max 33.2 — only 28 of them ≥15cm. Naively using `flood > 0` as the label would train the model on puddles.
2. **Apparent regime change in 2022** — nonzero rate collapses from ~1.5–3% to ~0.1%. But the ≥15cm rate is comparatively stable across all 7 years (0.004–0.044%), so the "collapse" is mostly the sub-5cm noise disappearing (likely sensor recalibration or a reporting change), not Bangkok flooding 20× less.
3. **NULL rate grew over time**: ~0% (2019–20) → ~2–3% (2021–22) → 8–11% (2023–25). NULLs are the literal string `"NULL"`, not blanks.
4. **Extreme class imbalance at the actionable threshold**: ≥15cm ≈ 15,000 timesteps total over 7 years (~0.02% of ~77M rows).
5. **UTF-8 BOM** on every header, **CRLF** line endings.
6. Station roster changes by year (99→107) — new stations have short history.

### 3.3 Solutions
1. Define the positive class on the CAP tier thresholds (≥5 / ≥15 / ≥30cm), not `> 0`. Confirm the event definition with the Data/GIS engineer (this was already on the sync checklist).
2. Consider **event-level labeling**: collapse consecutive ≥threshold timesteps into events with onset time; predict onset-within-horizon. This kills the noise problem and matches how alerts are consumed. Also consider a minimum-persistence rule (e.g. ≥2 consecutive 5-min readings) to drop single-tick spikes.
3. Coerce `"NULL"` → NaN at ingestion (`encoding="utf-8-sig"`, one shared cleaning function). Never impute the label — mask NULL-label timesteps out of loss/eval entirely.
4. Aggregate all 7 years for training; class-weight or focal-loss the classification head; evaluate with PR-AUC, F2, per-tier recall — never accuracy.
5. Handle the regime change by (a) including year/era as a feature or (b) validating that a model trained on 2019–23 doesn't degrade on 2024–25 specifically; at minimum keep the test window post-2022 so evaluation reflects the current sensing regime.
6. Per-station first-appearance table so lag features don't fabricate history for young stations.

### 3.4 EDA / feature engineering
EDA still needed: per-station NULL-rate map (is the 10% NULL concentrated in a few dead stations or spread?); event catalog (count, duration, peak, seasonality of ≥15cm events); monsoon seasonality profile (May–Oct) to pick the test window; inter-station event correlation (do floods co-occur → spatial pooling value).
Features from this dataset: lagged flood depth (autoregressive), time-since-last-flood, rolling max over 1h/3h, station identity embedding, hour-of-day/day-of-year (cyclic), station flood-climatology (historical event rate — careful: compute on train split only).

---

## 4. Dataset 2 — Rain (`Rain_2019-2025/`) — primary driver

### 4.1 What it holds
`rain_code, rain_name, site_timestamp, rf5min, rf15min, rf30min, rf1hr, rf3hr, rf6hr, rf12hr, rf24hr` — rainfall (mm) at 5-min cadence with 8 pre-computed rolling accumulations. 130 stations (2019–21) → 131 (2022–25). ~13.7M rows/year.

### 4.2 Problems
1. **Filename inconsistency**: `2019.csv`, `2020.csv`, then `Rain 2021.csv`…`Rain 2025.csv` (space + prefix). Any glob assuming one pattern silently drops years.
2. **Row deficit**: 2022–2025 files each have 13,770,433 rows vs the expected 131 × 105,120 = 13,770,720 — **287 rows missing**, station(s) unidentified. 2019 is exact.
3. **Implausible extreme**: rf24hr max = **762mm in 2023** — well beyond Bangkok's historical 24-h record (~350mm). Sensor spike or accumulation-reset artifact.
4. rf5min NULL rate grows over time: 0% (2019) → 2.4% (2022) → 3.4% (2025). Oddly, rf24hr shows 0% NULL even where rf5min is NULL — the accumulations are apparently computed/filled by BMA even over gaps, so **the accumulation columns may quietly interpolate over missing raw data**.
5. No station coordinates — can't yet join "rain here" to "flood there".

### 4.3 Solutions
1. Normalize filenames (or a hardcoded manifest) in the cleaning script, day one.
2. Locate the 287-row gap (per-station row count) and document; 287 rows ≈ one day of one station — negligible for training but must be known for the completeness claim to BMA.
3. Physical-plausibility clamp on all rf columns (e.g. rf5min ≤ 40mm, rf24hr ≤ 400mm → flag + NaN above); cross-check spikes against neighboring stations before deleting.
4. Don't trust rf-accumulations blindly where rf5min is NULL — either recompute accumulations from rf5min yourself (preferred, verifiable) or flag BMA-filled stretches with a binary "gap-filled" feature.
5. Until coordinates exist, join rain→flood stations by district-code inference from the station code (e.g. `RF.BBN.*` ↔ `FL.BBN.*` share a location prefix) — verify this prefix hypothesis in EDA; it likely gives a usable spatial join for free.

### 4.4 EDA / feature engineering
EDA: verify the station-code-prefix ↔ location hypothesis across the 4 networks (this is high-value — it may substitute for coordinates in the sprint); rain-vs-flood lag correlation (what lead time does rf1hr give on flood onset — sets the feasible forecast horizon); per-station NULL map; spike catalog; recompute-vs-provided accumulation consistency check.
Features: the rf accumulations *are* the classic rolling-sum features already computed — use rf1hr/rf3hr/rf6hr directly; add rain intensity deltas (rf1hr now vs 1h ago), area-aggregated rain (mean/max over nearby stations), antecedent wetness (rf24hr, plus multi-day sum built from dailies), monsoon-season flag.

---

## 5. Dataset 3 — Water level (`Water_2019-2025/`) — leading indicator

### 5.1 What it holds
`water_code, water_name, site_timestamp, wl_in, wl_out01, wl_out02` — canal water levels (m, apparently MSL datum; wl_in range −5.03…+3.73 in 2019) at 5-min cadence at canal/pump/gate sites. Largest dataset: 255 stations (2019–21) → 300 (2025), 26.8M → 31.5M rows/year, ~28GB total. Row counts exact (stations × 105,120), no truncation.

### 5.2 Problems
1. **`wl_out01`/`wl_out02` mostly NULL**: 80.5%/99.6% (2019) and 84.2%/99.7% (2025) — consistent across years. Not 100% though: some gate/pump stations do populate them.
2. `wl_in` NULL rate doubled over time: 4.9% (2019) → 9.0% (2025).
3. **Station names contain commas → quoted CSV fields** (e.g. `"จุดวัดคลองยายสุ่น ตอนถนนรัช..."`). Naive `split(',')` or awk breaks on this dataset (it silently worked on the other three). Real CSV parser mandatory.
4. Biggest file = biggest memory hazard: 28GB, unloadable naively.
5. Negative wl values are legitimate (below-MSL canal beds / drawdown), so no simple ≥0 sanity rule — harder to spot faults.
6. Datum/unit unconfirmed (m MSL assumed) — matters if anyone compares wl to DTM elevations.

### 5.3 Solutions
1. Per-station null-rate table for wl_out01/02; include the columns only for stations where populated (<some cutoff, e.g. <50% NULL), drop elsewhere. Don't blanket-exclude (the old roadmap's "100% NULL, exclude" is wrong).
2. Interpolate short wl_in gaps (≤30min) per station; mask longer gaps + add "sensor-out" indicator feature.
3. Cleaning script uses pandas/pyarrow CSV reader with proper quoting everywhere; ban shell-split analytics on Water.
4. **Convert everything to per-station-per-year Parquet in Phase 0** (this dataset is the reason); downstream work reads Parquet only.
5. Fault detection via per-station robust stats (rolling median ± k·MAD) instead of global range rules.
6. Confirm datum/units with Data/GIS engineer (same sync as label definition).

### 5.4 EDA / feature engineering
EDA: per-station wl_in completeness heatmap (station × month); which stations populate wl_out01/02 and are they gates/pumps (name-based classification); wl → flood lead-lag correlation for co-located (same-prefix) stations — this is the single most valuable EDA result for feature design; distribution of wl by season; stuck-sensor detection (long constant runs).
Features: wl_in lags and deltas (1h/3h rate-of-rise is the classic flood precursor), rolling mean/max/std over 1h/6h/24h, level-relative-to-station-percentile (normalizes datum differences across stations), gate head difference (wl_in − wl_out01 where populated → pumping/drainage state), count of nearby stations rising simultaneously.

---

## 6. Dataset 4 — Flow (`Flow_2019-2025/`) — secondary driver

### 6.1 What it holds
`flow_code, flow_name, site_timestamp, flow, wl, area, mean_velocity` — discharge (m³/s), local water level, cross-section area, velocity at 30 stations (constant all 7 years), 3.15M rows/year, 2.9GB. Exact row counts, no truncation.

### 6.2 Problems
1. **`FW.PKG.01` is broken in every year, both directions.** Verified: 390,753 rows across 2019–2025 with |flow| > 1,000 m³/s, ranging −3,297 to +3,801 — and all but 19 of them (which belong to `FW.LPW.01`) come from this one station. This extends the earlier finding (which only saw 2025 negatives): it's a persistent 7-year station fault, positive and negative, not a 2025 anomaly and not tidal backflow.
2. All-4-columns-NULL timesteps rising sharply: 5.0% (2019) → 11.2% (2024) → 15.9% (2025). The sensor network is degrading, and the test window (recent data) is the worst-affected.
3. Moderate negative flows elsewhere (~41K–325K rows/year) — these plausibly *are* tidal backflow (Chao Phraya is tidal) and are signal, not noise.
4. Only 30 stations — sparse coverage relative to 107 flood stations; many flood stations will have no nearby flow sensor.
5. `area` and `mean_velocity` are near-deterministic functions of flow/wl (flow ≈ area × velocity) — multicollinearity.

### 6.3 Solutions
1. Drop or fully mask `FW.PKG.01` (7 years of physically impossible values = unusable; decision to confirm with Data/GIS engineer, but the evidence is now decisive). Keep `FW.LPW.01` with a clamp (only 19 bad rows).
2. Treat all-4-NULL as masked timesteps (not per-column imputation, per roadmap §5.1); add "flow-sensor-out" indicator.
3. Keep moderate negative flows as-is — sign is informative (backflow = drainage impaired = flood-relevant).
4. Accept sparse coverage: use flow as area-level context features (nearest / district-aggregated), not required per-station input; the model must work for flood stations with no flow neighbor.
5. Use `flow` + `wl` and drop or PCA `area`/`mean_velocity` unless EDA shows independent signal.

### 6.4 EDA / feature engineering
EDA: per-station data-quality scorecard (null %, range, constant-runs) to decide the usable-30 list; verify flow ≈ area×velocity to confirm redundancy; tidal signature check (12.4h periodicity in negative flows near the river); flow→flood lead-lag for prefix-matched stations.
Features: flow and wl lags/deltas, negative-flow indicator + magnitude (backflow state), rolling 6h/24h means, district-aggregate flow.

---

## 7. Supporting datasets (briefer)

**Station registry (MISSING — build in Phase 0).** No coordinates exist for any of the 568 stations (107+131+300+30). Without it: no map, no spatial joins, no DTM features. Solution: approximate geocoding from Thai names + the shared district prefix in station codes (`*.BBN.*` = Bang Bon etc.); design as a swappable table so official BMA coordinates drop in later. EDA: extract the set of unique code prefixes, map to the 50 Bangkok districts, verify with the admin boundary layer.

**`DTM_1M/` (18GB) + SRTM rasters.** 1m terrain model + slope/aspect/hillshade. Use (once coordinates exist): static per-station features — elevation, local slope, relative height vs neighborhood (depression = ponding risk). Problem: unusable until the registry exists; 18GB needs windowed reads (rasterio), never full loads. Not required for the baseline model.

**`tha_admin_boundaries.gdb/.shp`.** Thai admin polygons for district-level aggregation and the dashboard's area views. Problem: national-scope file (733MB) — clip to Bangkok once, save the small subset.

**Live weather (Phase 4).** Everything above is *observed* data → the sprint model is a nowcaster (current conditions → near-future flood). True forecasting needs forecast rain as input: Open-Meteo for prototyping, ThaiWater/TMD for production. Out of sprint scope; note it honestly in the demo.

---

## 8. Cross-dataset issues (apply to all four time-series sets)

| Issue | Handling |
|---|---|
| `"NULL"` literal strings | Coerce at ingestion, single shared cleaner |
| UTF-8 BOM + CRLF | `encoding="utf-8-sig"`; pandas handles CRLF (shell tools don't) |
| 52GB total, unloadable | Phase-0 Parquet conversion, per station-year; all downstream reads Parquet |
| Station roster growth over years | First-appearance table; no fabricated history |
| Rising NULL rates toward the present (all datasets) | Report data-availability per year to BMA; sensor-out indicator features; ensure eval metrics computed only on observed labels |
| Spatial join without coordinates | Station-code district-prefix join (verify in EDA) until registry/geocoding lands |
| Chronological integrity | Train 2019–2024, test on a 2025 monsoon window (May–Oct); no shuffling, no future leakage in rolling features |

## 9. Recommended order of work

1. Phase-0 cleaning + Parquet conversion script (one pass over all 28 files; fixes NULLs/BOM/filenames; emits per-station completeness stats as a by-product).
2. Station registry + district-prefix join verification.
3. Label engineering: tiered/event-based label definition, sign-off with team.
4. EDA notebook run on Parquet: the lead-lag studies (rain→flood, wl→flood) that directly set lookback window and horizon feasibility.
5. Then feature pipeline → baseline ladder (persistence → LightGBM), per roadmap Phase 1.
