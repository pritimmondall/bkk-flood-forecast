# Bangkok Flood Forecast & Alerting System
## Master Build Specification — Version 3.0

**Prepared for:** Satoru Gojo · **Date:** 7 August 2026
**Status:** Research and design only. No code has been written for v3.0.
**Scope:** This document replaces every previous planning document in `docs/`. It is written to be handed straight back as a build order.

---

## How to read this document

Every number in Part B came from a **complete scan of all 28 raw CSV files (53 GB, 75.9 million flood rows)** performed on 7 August 2026. Nothing in Part B is estimated, sampled, or carried over from an earlier document.

Where a claim in an older document turned out to be **wrong**, it is corrected in §B.9 and flagged there as a **CORRECTION**.

> **Update, 8 August 2026.** Phase 0 has now been built and run. Five figures in
> Part B turned out to be wrong and are corrected in place below, each marked
> **CORRECTED**. The full comparison — what matched, what did not, and what the
> notebooks found that this document never mentioned — is in
> `docs/reports/phase0_verification.md`, and every number now regenerates from
> `notebooks/00`–`02`.

Where something **cannot be verified** — for example whether BMA will grant access to a data feed — it is marked **UNVERIFIED** and never presented as fact.

Plain language is used throughout. Where a technical term is unavoidable, it is explained the first time it appears.

---

# PART A — ORIENTATION

## A.1 What we are building, in one paragraph

Bangkok has about 107 road sensors that measure how deep the water is on the street, 131 rain gauges, 300 canal water-level sensors and 30 canal flow meters. All of them report every five minutes. We have seven years of that data (2019–2025). We are building a system that (a) shows what is happening right now on a map, (b) predicts which roads will flood 1, 3 and 6 hours from now, (c) turns those predictions into standard emergency messages (CAP), and (d) is honest about how often it will be wrong.

## A.2 The three products

The project is really three separate things that share data. They should be built and improved independently, and this separation is the single most important structural decision in the document.

| Product | What it is | What it needs to improve |
|---|---|---|
| **The forecaster** | A model that predicts flood depth and flood risk at sensor sites | Better rainfall data. Nothing else comes close. |
| **The dashboard** | A map + charts + alert console for a duty officer | Station coordinates and canal GIS layers |
| **The alerting** | CAP-standard messages routed to responders | An authorisation decision from BMA, not code |

They fail for different reasons and improve on different clocks. Bundling them into one roadmap is what made the previous versions of this project confusing.

## A.3 The honest one-line summary

> With the data we currently hold, this system can be an **excellent monitor** and a **modest forecaster**. The gap between those two is not a software problem — it is a rainfall-resolution problem, and it is measurable.

---

# PART B — THE DATA, VERIFIED

## B.1 What we hold

Four sensor datasets, seven years each, five-minute cadence, one CSV per year.

| Dataset | Folder | Files | Size | Rows | Stations (2025) |
|---|---|---|---|---|---|
| Rainfall | `data/Rain_2019-2025/` | 7 | 12.7 GiB | 96,153,700 | 131 |
| Canal water level | `data/Water_2019-2025/` | 7 | 27.5 GiB | 198,730,656 | 300 |
| Canal flow | `data/Flow_2019-2025/` | 7 | 2.8 GiB | 22,092,480 | 30 |
| Road flood depth | `data/Flood_2019-2025/` | 7 | 8.1 GiB | 75,932,352 | 107 |
| **Total** | | **28** | **51.1 GiB / 54.9 GB** | **392,909,188** | **568 unique** |

Supporting spatial data:

| Asset | Path | What it actually is |
|---|---|---|
| 1 m DTM | `data/DTM_1M/DTM_1M.tif` | 13.9 GB, EPSG:32647 (UTM 47N), 1 m pixels, 66,227 × 52,321. Covers 100.325–100.941 E, 13.481–13.958 N — **the whole of Bangkok**. Has 8 overview levels built in. |
| SRTM DEM | `data/output_SRTMGL1.tif` | 31 m, EPSG:4326, int16 |
| Derived terrain | `data/viz/*.tif` | slope, aspect, hillshade, roughness — all from the 31 m SRTM |
| District boundaries | `data/gis/bangkok_districts.geojson` | 50 khet polygons |
| Sub-district boundaries | `data/gis/bangkok_subdistricts.geojson` | khwaeng polygons |
| Thailand admin | `data/tha_admin_boundaries.shp/`, `.gdb/` | admin0–admin3, national |
| Station registry | `data/station_registry_full.csv` | 568 rows — see §B.8, treat with care |

## B.2 Exact file schemas

All four files share the same three leading conventions: a **UTF-8 byte-order mark on the header line**, a `site_timestamp` column with millisecond precision, and the literal text `NULL` for missing values.

**Rain** — `rain_code, rain_name, site_timestamp, rf5min, rf15min, rf30min, rf1hr, rf3hr, rf6hr, rf12hr, rf24hr`
Rolling accumulations in millimetres. `rf1hr` is the rain that fell in the last hour, not since the hour began.

**Water** — `water_code, water_name, site_timestamp, wl_in, wl_out01, wl_out02`
Water level in metres against an unknown datum (see §B.6). `wl_in` = level on the inflow side of a structure, `wl_out01/02` = outflow side.

**Flow** — `flow_code, flow_name, site_timestamp, flow, wl, area, mean_velocity`
Discharge m³/s, stage m, wetted cross-section m², velocity m/s. Note `flow ≈ area × mean_velocity`, so three of the four columns are not independent.

**Flood** — `flood_code, flood_name, site_timestamp, flood`
**`flood` is the target variable: water depth on the road surface in centimetres.**

`*_name` columns are Thai free text (place descriptions, not station names) and contain commas — a quoted CSV parser is mandatory.

## B.3 Coverage and completeness — verified

**The time grid is essentially perfect.** Across all 392,909,188 rows there are **zero duplicate `(station, timestamp)` pairs** — verified, not assumed, because a repeated timestamp would silently corrupt every lag feature built later.

**CORRECTED.** An earlier draft said *every* station-year has exactly 105,120 rows (105,408 in leap years). It is 3,730 of 3,736. The six exceptions are two different stories, and neither is alarming:

- **FL.MBR.01 and FL.DST.08 in 2021** are 38–39% complete because those sensors were *installed* on 14 and 11 August 2021. Nothing is missing; the sensor did not exist. Per-station statistics for 2021 must be computed over the station's lifetime, not the calendar year, or these two look like catastrophic outages.
- **RF.PYT.02 in 2022–2025** is short by exactly 287 rows every year: the export truncates 31 December at 00:00. A repeatable export bug on one rain gauge, worth mentioning to BMA, and 0.033% of the archive.

Missingness lives in the **values**, not the rows, and it is getting worse:

| Year | Flood `flood` null % | Water `wl_in` null % | Rain `rf1hr` null % | Flow `flow` null % |
|---|---|---|---|---|
| 2019 | 0.00 | 4.86 | 0.00 | 5.04 |
| 2020 | 0.03 | 0.86 | 0.08 | 3.44 |
| 2021 | 1.89 | 1.77 | 1.05 | 6.63 |
| 2022 | 2.92 | 4.90 | 2.41 | 5.55 |
| 2023 | 10.11 | 5.24 | 2.51 | 7.92 |
| 2024 | 8.20 | 11.65 | 1.97 | 11.22 |
| 2025 | **10.70** | 9.02 | 3.43 | **15.93** |

**NOTE — This is a new finding and it matters.** The sensor network's data quality degrades sharply from 2023 onward. Since 2023–2025 are exactly the years used as test years in a chronological split, the model is being tested on the *worst* data in the archive. Every evaluation number must be read with that in mind, and `*_offline_share` features must be in the model so it can tell the difference between "no flood" and "no sensor".

35 flood station-years (of 723) are more than 50% null. 103 water station-years (of 1,889) are more than 50% null.

**Station counts by year** (verified):

| Year | Flood | Rain | Water | Flow |
|---|---|---|---|---|
| 2019 | 99 | 130 | 255 | 30 |
| 2020 | 99 | 130 | 255 | 30 |
| 2021 | 102 | 130 | 255 | 30 |
| 2022 | 102 | 131 | 262 | 30 |
| 2023 | 107 | 131 | 265 | 30 |
| 2024 | 107 | 131 | 297 | 30 |
| 2025 | 107 | 131 | 300 | 30 |

The network **grows**: 8 flood stations and 45 water stations appear part-way through the archive. A model that treats station identity as a categorical feature will have no history for new stations. This is a real cold-start problem and §E.7 addresses it.

## B.4 The target variable — the numbers that define the whole project

Across all 75,932,352 flood rows:

| Condition | Rows | Share | Odds |
|---|---|---|---|
| `flood` is null | 3,782,275 | 4.98% | — |
| `flood` = 0 exactly | 71,492,547 | 94.15% | — |
| `flood` > 0 | 657,530 | 0.866% | 1 in 115 |
| `flood` ≥ 5 cm | 50,929 | 0.0671% | **1 in 1,491** |
| `flood` ≥ 15 cm | 15,024 | 0.0198% | **1 in 5,054** |
| `flood` ≥ 30 cm | 3,262 | 0.0043% | **1 in 23,278** |
| `flood` < 0 | 0 | 0% | — |

Maximum depth ever recorded: **148.8 cm**. Minimum: 0.0.

**Why `flood > 0` cannot be the definition of a flood.** 0.87% of rows are non-zero but only 0.067% reach 5 cm. The gap is sensor noise — millimetre readings from a device sitting on a wet road. Any threshold must sit above that noise floor.

**Flood events, counted properly.** An excursion is a run of consecutive readings at or above a tier. The full definition then applies three rules: keep excursions of at least **2 consecutive readings**, **merge** those less than **60 minutes** apart, and discard anything under **10 minutes**.

**CORRECTED.** An earlier draft of this table applied only the first rule. The chain, measured in `notebooks/02`:

| Stage | 5 cm | 15 cm | 30 cm |
|---|---|---|---|
| Raw excursions | 5,281 | 1,469 | 342 |
| After persistence (≥2 readings) | 3,749 | 999 *(the figure quoted before)* | 179 |
| **After merge + minimum duration** | **3,135** | **837** | **132** |

| Year | ≥5 cm events | ≥15 cm events | ≥30 cm events | Stations hit (15 cm) |
|---|---|---|---|---|
| 2019 | 367 | 97 | 27 | 45 |
| 2020 | 432 | 110 | 17 | 38 |
| 2021 | 593 | 138 | 15 | 50 |
| 2022 | **774** | **235** | 30 | 56 |
| 2023 | 384 | 99 | 17 | 56 |
| 2024 | **253** | **46** | **7** | 25 |
| 2025 | 332 | 112 | 19 | 49 |
| **Total** | **3,135** | **837** | **132** | 83 distinct |

> **The single most important number in this document: there are 837 flood events at the 15 cm tier in the entire seven-year archive.** Not 837 per year — 837 in total, across all of Bangkok, across seven years. At 30 cm there are 132.

This governs the entire model strategy (§E.6). It is far too little data to train a Transformer or a Temporal Fusion Transformer to beat a gradient-boosted tree, and pretending otherwise would waste months.

**Event duration. CORRECTED.** An earlier draft said 15–25 minutes; that was the median *excursion*, before merging. The median **event** at 15 cm lasts **45 minutes** (p25 = 25, p75 = 95, p90 = 185). **61% are over within an hour and 90% within three.** These are still flash events, not slow river floods — which is why lead time is hard and why a 6-hour horizon is close to climatology.

**The definition was stress-tested rather than asserted.** Varying the rules moves the 15 cm count from 999 (no merging) to 569 (6 readings, 3-hour merge). The configured values sit at the elbow of both curves — the full grid is in `docs/reports/phase0/event_definition_sensitivity.csv`.

**Year-to-year variance is enormous.** 2022 had 235 events at 15 cm; 2024 had 46. A model validated on 2024 is being validated on almost nothing. Any single-number performance claim across years is misleading — always report the spread.

**Flooding is extremely concentrated.** 12 of the 107 flood stations have never recorded a single *reading* ≥15 cm, and **24 have never recorded an event** at that tier. The ten worst sites produce **298 of the 837 events — 36% of all flooding from 9% of the sensors.** Worst: FL.SMI.01 (48 events), FL.PWT.02 (38), FL.DDG.02 (32), FL.SLG.03 (31), FL.DDG.01 (29).

**The most flood-prone sites** (readings ≥15 cm, all years): FL.PWT.02 (1,269), FL.LSI.03 (797), FL.CTC.05 (781), FL.SLG.03 (682), FL.PYT.02 (617), FL.BKM.01 (546), FL.SMI.01 (518), FL.DDG.02 (509), FL.DDG.06 (432), FL.STN.03 (429).

## B.5 Rainfall data — quality notes

- 131 gauges, 51 distinct district-code prefixes.
- Maximum `rf5min` observed anywhere: **30.0 mm**. **CORRECTED.** An earlier draft read this as a shared device ceiling across the gauge network. It is not: **one gauge of 131 reaches 30.0 mm**, and the other 130 top out between 12 and about 25 mm in a smooth distribution of station maxima. There is no cap — there is one gauge that saw a genuinely extreme five minutes. Still worth mentioning to BMA; no longer a data-request item.
- Maximum `rf1hr`: 124.0 mm. Plausible for Bangkok.
- Maximum `rf24hr`: **762.0 mm**, at RF.BKY.02 in 2023. That station's own `rf1hr` maximum is 73 mm and `rf5min` maximum 13 mm — 762 mm in 24 hours is not consistent with those. **Treat as a data error**, null it, and flag it.
- The `rf*` columns are **rolling accumulations produced by BMA**, which means some are gap-filled. A filled value is indistinguishable from a measurement unless we derive our own accumulations from `rf5min`. **Recommendation: recompute rf15min…rf24hr ourselves from rf5min and keep the BMA versions only as a cross-check.**

## B.6 Water and flow — the datum problem

- `wl_in` ranges from **−5.22 m to +4.00 m**. Negative values are normal for canals measured below a local reference.
- **We do not know what the reference is.** Mean sea level, canal bed, or an arbitrary per-station benchmark — nobody has told us. Without the datum, an absolute level is uninterpretable, so **only changes in level can be used as model inputs**. "The canal is 30 cm below its bank" is a much better predictor than "the canal rose 8 cm", and we cannot compute the first one.
- `wl_out01` is **81.8% null** and `wl_out02` is **99.6% null**. Treat `wl_out02` as unusable and `wl_out01` as sparse.
- Flow: two stations operate at a completely different scale from the rest. **FW.PKG.01** ranges −3,297.7 to +3,801.8 m³/s and **FW.LPW.01** reaches 2,916.7. These are river-scale discharges (Chao Phraya), not canal-scale. They are **not faulty** — they are the wrong scale to average with canals. Exclude them from any citywide canal aggregate and expose them separately as "river discharge".
- **FW.SSM.01 records exactly 0.00 for every reading in every year.** Dead sensor. Drop it.

## B.7 The spatial join — why water and flow are nearly useless right now

Station codes look like `TYPE.PREFIX.NN`. For rain and flood the prefix is a **district abbreviation** (BBN = Bang Bon). For water and flow the prefix is a **canal name abbreviation** (SSB = Saen Saep, KPM = Khlong Prem…). Those are different naming systems.

Verified coverage of the **33 districts that have flood sensors**:

| Source | Districts covered | Consequence |
|---|---|---|
| Rain (51 prefixes) | **33 / 33 (100%)** | Rainfall can be joined per district ✅ |
| Water (163 prefixes) | **13 / 33 (39%)** | Water must enter as a **citywide average** ❌ |
| Flow (30 stations) | **3 / 33 (9%)** | Flow must enter as a **citywide average** ❌ |

This is the second-biggest limitation in the project, and it is fixed by a spreadsheet of coordinates, not by modelling.

## B.8 The station registry — read the fine print

`data/station_registry_full.csv` has 568 rows but is **not a source of truth**. It was constructed by inference in a previous version:

| Confidence | Rows | What the coordinates actually are |
|---|---|---|
| High | 264 | District centroid, inferred from a shared code prefix |
| Medium | 128 | Sub-district centroid from a name match |
| Low | 9 | Weak name match |
| **Unresolved** | **167** | **No coordinates at all** (`lat` is null) |

**Even the "High" rows are district centroids, not sensor positions.** Every flood station in Bang Bon carries the identical coordinate 13.646, 100.370. On a map they stack on top of each other. This is fine for a district choropleth and **completely unfit** for spatial interpolation, distance features, or a "flood surface".

166 of the 167 unresolved rows are water stations whose canal-coded prefix cannot be decoded to a district from the name alone.

## B.9 Corrections to previous documents

These claims appear in `docs/technical_roadmap.md`, `docs/data_inventory.md`, `docs/model_report.md` or `docs/data_requests.md` and are wrong or incomplete.

| Previous claim | Verified reality |
|---|---|
| "Terrain is 31 m SRTM, which cannot resolve road dips" and "LiDAR road elevation — BMA may already hold this" | **We already hold a 13.9 GB, 1 m DTM covering the entire Bangkok boundary** (`data/DTM_1M/`). It was never used because it is large and in UTM 47N while everything else is in WGS84. This is not a data request — it is a processing job. |
| "Class imbalance: roughly 1 positive row in 4,000 at the 15 cm tier" | **1 in 5,054** over the full archive. Year-dependent: 1 in 2,251 in 2022, 1 in 25,120 in 2024. |
| "There is no live BMA sensor API" | BMA's Drainage and Sewerage Department runs a **public live portal at `pumps.bangkok.go.th`** showing 148 pump-station water levels updating every ~5 minutes, with a queryable history (≈10.3 M records) and per-station pages. Station codes use the same `PH.<district>.NN` convention — **27 of our 33 flood-district prefixes appear there**. Whether it may be used programmatically is **UNVERIFIED** and is a permissions question. See §D.1. |
| "`FW.PKG.01` reads ±3300 m³/s — excluded as an outlier / faulty sensor" | Correct to exclude, but **FW.LPW.01 (max 2,917 m³/s) has the same problem and was not mentioned**. Also **FW.SSM.01 is flat zero for seven years** and was not mentioned. |
| Data inventory says "54.9 GB", "~300 water sites, ~107 flood sites" | Sizes confirmed (≈54.8 GB). Station counts confirmed, but the counts **change by year** and the tables in that document collapse that. |
| "Station registry: 568 stations, 401 placed geographically" | Correct count, but "placed" means *district centroid*. 167 have no coordinates at all. The document does not make the centroid caveat prominent enough. |
| Nothing in any document mentions data-quality degradation over time | Null rates roughly **triple between 2022 and 2025** across flood, water and flow. |

## B.10 What we do not have

| Missing | Why it matters | Priority |
|---|---|---|
| **Radar rainfall (TMD)** | Our rain is a district average; Bangkok floods from 2–5 km convective cells. Averaging over a 20 km² district removes the peak that causes the flood. Rainfall carries ~76% of the forecasting signal. | 1 |
| **Station coordinates + datum + install height** | Turns water and flow from citywide averages into local features; makes the map real; makes `Depth = WaterLevel − RoadElevation` computable. | 2 |
| **Canal network topology** | Which canal drains into which, with gates. Unlocks upstream features and graph models. | 3 |
| **Pump and gate operation logs** | The drainage system has an operator. A model blind to pump state is predicting a system while ignoring its controller. | 4 |
| **Chao Phraya tide gauge (measured)** | High tide holds the drainage gates shut. We can reconstruct tidal *phase* from lunar periods but not *height*. | 5 |
| **Independent flood reports** | Our labels are sensor-only. A flood where there is no sensor never happened, as far as the model and the evaluation are concerned. | 6 |
| **2026 data** | The 2025 holdout has already been used. A fresh year restores a genuinely sealed test. | 7 |

---

# PART C — FEASIBILITY MATRIX

This is the section you asked for: for each feature, **can we build it accurately, approximately, or not at all** — and what would change that.

**Legend — YES** = accurate and buildable now. **PARTLY** = buildable, but the accuracy claim must be qualified. **NO** = not possible with the data we currently hold.

## C.1 The ten requested application features

### 1. Interactive Bangkok Map — PARTLY (approximate)

| | |
|---|---|
| **Can do** | 50-district and sub-district choropleth from verified GeoJSON. District-level colouring by rainfall, risk, and observed flood. Terrain/hillshade base layer from the 1 m DTM. |
| **Cannot do** | Place a station marker at its real location. All 401 "placed" stations sit on district or sub-district centroids, so multiple sensors stack on one point. |
| **Needed** | A lat/lon spreadsheet for 568 sensors. |
| **Workaround** | Show district polygons as the primary geometry and render stations as a *list panel* keyed to the highlighted district, not as map pins. If pins are required, jitter them within the district and mark every one with `coord_quality: "district_centroid"` in the API response so the UI can show a dashed marker. |

### 2. Flood Forecast (1 h / 3 h / 6 h) — YES at sensor sites, NO anywhere else

| | |
|---|---|
| **Can do** | Per-station probability of exceeding 5 / 15 / 30 cm at +1 h, +3 h, +6 h, with calibrated probabilities and honest recall figures. This is the core of the project and the data supports it. |
| **Cannot do** | Forecast at a road with no sensor. There are 107 flood sensors for ~1,569 km² and 50 districts. |
| **Needed** | More sensors, or an independent report stream to learn a spatial model from. |
| **Workaround** | Present forecasts as *station-level* and roll up to district-level as "the worst forecast among sensors in this district" (the P95 the supervisor's scheme asks for). Never imply coverage between sensors. |
| **Honest limit** | Prior measured performance: at 15 cm / 1 h, recall ≈ 0.55 with a range of 0.39–0.66 across years; at 6 h recall ≈ 0.17. Onset recall (rows where the road was dry) is far lower than headline recall. |

### 3. Water Level Monitoring — PARTLY (approximate)

| | |
|---|---|
| **Can do** | Time series and rate-of-change for 300 canal sensors. Rising/falling status. "How many sensors in the network are rising right now." |
| **Cannot do** | Say whether a canal is *close to overflowing* — that needs the datum and the bank height. Cannot place the sensor on the map (only 13 of 33 flood districts are covered by a decodable water prefix). |
| **Needed** | Datum + bank/deck elevation + coordinates per station. |
| **Workaround** | Use a **per-station empirical percentile** instead of an absolute threshold: "this canal is at its 98th percentile for the last two years." That is hydrologically weaker but immediately available and defensible. |

### 4. Rainfall Monitoring — YES — accurate at district level

| | |
|---|---|
| **Can do** | 131 gauges, five-minute cadence, 1/3/6/12/24-hour accumulations, joined to **100% of the districts that have flood sensors**. Live-style district rainfall panel. |
| **Cannot do** | Show rainfall between gauges. A gauge network of 131 over 1,569 km² is roughly one gauge per 12 km²; convective cells are 2–5 km across. |
| **Needed** | TMD radar (1 km grid, 5–15 min). |
| **Workaround** | IDW interpolation between gauges is *possible* but should be labelled clearly as interpolation, and it will miss exactly the cells that matter. Open-Meteo / ECMWF forecast rainfall is a genuinely useful complement and is free — a previous run measured archived forecast rain correlating with 6-hour flood labels roughly three times more strongly than past gauge rain. |

### 5. Flow Monitoring — PARTLY (approximate)

| | |
|---|---|
| **Can do** | 30 canal flow meters with discharge, stage, area and velocity. Detect **backflow** (negative flow), which is a genuine early warning signal. |
| **Cannot do** | Localise it — only 3 of 33 flood districts have a decodable flow prefix. |
| **Gotcha** | Exclude FW.PKG.01 and FW.LPW.01 from canal aggregates (river scale). Drop FW.SSM.01 (dead). That leaves **27 usable canal flow meters.** |
| **Needed** | Coordinates. |

### 6. Flood Risk Dashboard — YES — accurate

All KPIs the supervisor's scheme asks for are computable: Peak Risk %, Peak Time, Time to Warning, area P95 and area-weighted mean — **provided "area" means "district", not "arbitrary polygon"**.

### 7. Historical Trends — YES — accurate

Seven years, complete five-minute grid, no duplicates. Monthly/seasonal flood frequency, per-station event history, year-on-year comparison, rainfall–flood relationship — all fully supported. This is the strongest part of the data.

### 8. CAP Alerts — YES for the schema, PARTLY for the geography

| | |
|---|---|
| **Can do** | Full CAP 1.2 compliance against the supervisor's schema. Bilingual Thai/English `headline`, `description`, `instruction`. Correct `urgency`/`severity`/`certainty` derived from the forecast horizon and tier (see §E.11). |
| **Cannot do** | Give a precise `<circle>` or `<polygon>` for the affected area. |
| **Workaround** | Use `<geocode>` with the district code plus a `<polygon>` of the **district boundary**. That is honest, standards-compliant, and actually more useful to a responder than a false 500 m circle. |
| **Must do** | `status` stays `Test` until BMA formally authorises. This should be a config flag that requires a deliberate change, not a UI toggle. |

### 9. Flood Hotspots — YES — accurate

Verified and ready: event counts per station per tier per year are already computed (§B.4). Hotspot ranking, risk timeline and "rapidly rising" detection are all directly supported.

### 10. Forecast Charts — YES for risk, PARTLY for depth

| | |
|---|---|
| **Risk chart** | Fully supported. Line = calibrated probability, background bands = Normal/Watch/Warning/Critical, KPI chips = Peak Risk, Peak Time, Time to Warning. |
| **Depth chart** | Supported, but the **uncertainty band is the known weak point**. A previous run produced P05–P95 bands covering 99.6–99.9% of outcomes against a 90% target — the bands are so wide they carry no information. §E.8 specifies the fix (pinball-loss-optimised quantile models with coverage as an explicit acceptance criterion). Do not ship a depth band that has not passed a coverage test. |

## C.2 The supervisor's Dashboard Scheme, panel by panel

### Panel 1 — Situation Summary — YES
All four components (current rain, active flooding, canal levels, upstream flow) are directly computable. Threshold-priority ordering is trivial.

### Panel 2 — Current Flood Map (Observed) — PARTLY as points, NO as a surface

The scheme asks for a **continuous flood surface via IDW / Kriging / graph interpolation**. This is not defensible with our data, for three reasons:

1. **107 points over 1,569 km²** is roughly one sample per 15 km². Interpolating a surface from that is drawing, not measuring.
2. **The coordinates are district centroids**, so multiple stations share one point — interpolation is mathematically ill-posed.
3. **Urban flood depth is not a smooth spatial field.** It is controlled by kerb heights, drain inlets and 20–50 cm road dips. Two points 300 m apart can differ by 30 cm. Kriging assumes spatial correlation that does not exist here at the scales we can sample.

**Recommendation:** build the panel as a **district choropleth + station markers**, and record in the document that a continuous surface was considered and rejected on evidence. If a surface is politically required, produce it from the **1 m DTM's depressions** (a "where water would collect" map, which is real terrain information) rather than from interpolated sensor values — and label it as susceptibility, not observed depth.

### Panel 2 formula — `Flood Depth = Water Level − Road Elevation` — NO — not computable today; PARTLY once coordinates arrive

We have the **Road Elevation half**: the 1 m DTM covers all of Bangkok. What is missing is (a) the sensor's coordinate so we can sample the DTM under it, and (b) the water-level datum so the two numbers are in the same vertical reference. Both are in the same data request.

Note also that the `flood` column we already have **is** road depth, measured directly. The formula is only needed to extend depth to places without a flood sensor.

### Panel 3 — Forecast Flood Risk Map (next 3 h) — PARTLY as districts, NO as a surface
Same reasoning as Panel 2. Per-station and per-district forecasts, yes. A smooth 3-hour flood surface, no.

The scheme's "recalculate every 5 minutes" is achievable in replay mode today and in live mode only once a feed exists (§D.1).

### Panel 4 — Forecast Chart, Flood Risk — YES
Fully supported, including the P95-within-area primary line and area-weighted-mean secondary, at district granularity.

### Panel 6 — Water Levels (Hydrological Trend) — PARTLY — mixed

| Sub-component | Status |
|---|---|
| Canal water levels (Saen Saep, Lat Phrao, Bang Sue) | YES — in our data — prefixes SSB, LPW, BSU all present |
| Chao Phraya river levels (Phra Phuttha Yodfa, Rama VII, Bang Na) | NO — not in our data. FW.PKG.01 is a Chao Phraya gauge but only one point. Available externally from RID / ThaiWater — **UNVERIFIED** whether coverage matches those three stations. |
| Sea level / tide (m MSL) | NO — not in our data. Tidal *phase* can be reconstructed from lunar periods (M2 = 12.42 h, spring–neap = 29.53 d) — that is real physics and free, but gives timing without height. |
| "Rapid rate of rise" alerts | YES |
| 3-hour water-level forecast | PARTLY — a separate small model; feasible but not yet built or evaluated |

### Panel 9 — Major Hotspots — YES
All three criteria (rapid rise, rainfall over threshold, forecast probability > 95%) are computable.

### Panel 10 — Forecast Chart, Flood Depth — PARTLY
Supported; the impact thresholds (5/15/30 cm) match our tiers exactly. Weak point is the uncertainty band — see C.1 §10.

### Items in the scheme that are NO outright

| Item | Why | Alternative |
|---|---|---|
| **CCTV AI flood detection** | We have no camera access, no video, no annotation budget | Traffy Fondue citizen photo reports (§D.2) give a similar signal without any CV work |
| **Radar nowcasting** | No radar data held | TMD registration (§D.3); Open-Meteo forecast rain as a free stand-in; RainViewer imagery for display only |
| **Soil Moisture Index / Evapotranspiration** (shown in the scheme's screenshots) | Not in any of our four datasets | Already confirmed with the supervisor as illustrative template imagery, not a requirement. Ignore. |
| **Per-station calibrated thresholds** (as in the Phrae reference system) | Would need 2+ years of clean history per station; 45 water stations and 8 flood stations are younger than that | Use the universal 5/15/30 cm tiers now; add per-station percentile thresholds as a phase-2 upgrade for stations with enough history |

## C.3 Summary table — what to promise

| Capability | Verdict | Blocking input |
|---|---|---|
| Historical analysis & trends | YES — ship it | — |
| District rainfall monitoring | YES — ship it | — |
| Hotspot ranking | YES — ship it | — |
| Per-station flood forecast 1 h | YES — ship it with stated recall | — |
| Per-station flood forecast 3 h / 6 h | PARTLY — ship as Watch only | Radar rainfall |
| CAP message generation | YES — ship in `Test` mode | BMA authorisation |
| Risk / depth forecast charts | YES risk / PARTLY depth band | Quantile recalibration |
| Canal level monitoring | PARTLY — relative changes only | Datum + bank height |
| Flow / backflow monitoring | PARTLY — citywide only | Coordinates |
| Station markers at true positions | NO | Coordinates |
| Continuous observed flood surface | NO | ~10× sensor density |
| Continuous forecast flood surface | NO | Coordinates + radar + topology |
| `Depth = WaterLevel − RoadElevation` | NO → PARTLY | Coordinates + datum (DTM already held) |
| Chao Phraya / tide panel | NO → PARTLY | External RID / Hydrographic feed |
| Live 5-minute operation | NO → YES | A live feed (§D.1) |
| CCTV detection | NO | Out of scope — do not promise |

---

# PART D — EXTERNAL DATA SOURCES

Everything below was checked on 7 August 2026. "Reachable" means the URL responded with the described content. **It does not mean we have permission to use it programmatically** — that is a separate conversation for every source.

## D.1 BMA Drainage pump portal — the most important find

**`https://pumps.bangkok.go.th`** — reachable, live, public, no login required for viewing.

| What it shows | Detail |
|---|---|
| Stations | **148 pump stations**, all of Bangkok |
| Live values | Water level in metres, timestamps updating on a ~5-minute cadence (observed live during this research) |
| Station codes | `PH.<district>.NN` — e.g. `PH.DDG.06`, `PH.BBN.01`, `PH.SMI.01`. **27 of our 33 flood-district prefixes appear** |
| History | A date-range query page reporting ≈10.3 million records |
| Per-station pages | `/stations/{id}`, ids observed from 1 to ~150 |
| Map | The homepage renders a station map, so **coordinates exist on the server** |

**Why this is significant.** The previous roadmap's headline blocker was "there is no live BMA sensor API." There is a live, public BMA drainage data source with the same station-coding convention as our archive, plus the pump-station coordinates we have been asking for.

**What is UNVERIFIED and must be established before building on it:**

1. Whether an official JSON endpoint exists (a plain `/api/stations` guess returned nothing).
2. Whether BMA permits automated collection. **Ask before scraping.** This is a government system and an unauthorised scraper is a bad first impression in a project whose whole purpose is a BMA partnership.
3. Whether pump-station water level is the same measurement as our `wl_in`, and on what datum.
4. Whether pump *operating state* (on/off, capacity) is exposed anywhere.

**Action:** put this at the top of the BMA meeting agenda, framed as *"you already publish this — may we consume it, and is there an API?"* rather than as a new data request. It is a much easier ask.

## D.2 Traffy Fondue — citizen flood reports

**`https://publicapi.traffy.in.th/teamchadchart-stat-api/geojson/v1`** — verified working, returns GeoJSON.

Each feature carries: point coordinates, `timestamp`, `district`, `subdistrict`, `description` (Thai free text), `problem_type_fondue` (a category list that includes flooding — `น้ำท่วม` / *nam thuam*), `photo_url`, `state`, `ticket_id`, plus an `ai` block with an auto-summary and category confidences.

**Why it matters more than it looks.** This is the **independent ground truth** the project has never had. Our flood labels come only from 107 sensors; a flood on a road without a sensor is invisible to both the model and the evaluation. Traffy reports are geolocated, timestamped, photographed and citywide.

**Uses, in order of value:**

1. **Evaluation, not training.** Ask: when the model said "no flood", did citizens report flooding anyway? That quantifies, for the first time, how much flooding the sensor network misses.
2. Populate the scheme's "Observed Flood reports / citizen reports" layer.
3. Long term, a weak-supervision label source for districts without sensors.

**Caveats:** reporting is biased toward populated, connected areas; a report means "someone complained", not "the depth was 15 cm"; timestamps are report time, not onset time; coverage before ~2022 is thin. Historical bulk access is **UNVERIFIED** — the live endpoint is paginated and the archive may need a request to NECTEC.

## D.3 TMD weather radar

Bangkok is covered by TMD radars including **Nong Chok** and **Nong Khaem** (`weather.tmd.go.th/bma_nck.php`, `.../bma_nkm.php`) and Khao Khiao (240 km range). Imagery is public.

**A documented public API for gridded radar values was not found.** What is public is rendered PNG imagery. Deriving rainfall rates from coloured PNGs is possible but lossy and fragile — do not build a training pipeline on it.

**Action:** formal registration/request to TMD for gridded product access, historical archive + live. Frame it as a BMA-endorsed request. This remains the single highest-value missing input.

**Interim substitutes:** Open-Meteo (free, no key) — both its archived-forecast and ERA5 products are pulled in Phase 2, kept strictly separate. **Resolution caveat that must travel with them:** IFS HRES is ~9 km and ERA5 ~25 km, while Bangkok is ~40 km across, so neighbouring districts share grid cells. These are regional series labelled by district, not district-specific rainfall — which is precisely why radar stays priority 1. Full source-by-source status and the BMA ask-list: `docs/reports/phase2/external_sources.md`.

## D.4 ThaiWater / HII

**`https://standard.thaiwater.net`** — verified reachable. Published by HII (สสน.), this is Thailand's **national water-data exchange standard**, and it is important to be precise about what it is: it specifies *how* agencies should publish water data, not a single endpoint you can call today.

It contains two parts, both directly useful:

1. **Data-exchange standard** — RESTful API specifications for rainfall, water level / discharge (น้ำท่า), reservoir storage, water quality and **station information**, plus CSV and FTP exchange formats, unit conventions, coordinate conventions, datum conventions for water-level measurement (`การวัดระดับน้ำ`) and quality-control flags.
2. **Alerting standard** (`มาตรฐานข้อมูลน้ำเพื่อการเตือนภัย`) — national definitions of flood (`น้ำท่วม`), alert levels and their colour symbols, and station criteria for alerting.

**Two concrete uses.**
- **The datum question in §B.6 may already have a national answer.** The `การวัดระดับน้ำ` page defines how water level should be referenced. Read it before asking BMA — the answer may be "MSL, per the national standard".
- **The alerting-level definitions should be checked against our 5/15/30 cm tiers and the DDPM mapping in §E.11.** If Thailand has a national alert-level standard, aligning to it is far stronger than inventing our own.

**Value for Panel 6:** the most likely legitimate route to Chao Phraya river levels and tide. Actual Bangkok station coverage and which agency serves it is **UNVERIFIED** — the site documents the standard; finding the live RID / HII endpoints that implement it is a follow-up task. The documentation is in Thai.

## D.5 Bangkok Open Data & BMA GIS

| Source | What to look for |
|---|---|
| `data.bangkok.go.th` | Traffy Fondue complaint datasets; sub-district boundaries and centroids (already used to build the station registry) |
| `cityplangis.bangkok.go.th/cpdPortal/` | City Planning GIS portal — likely home of canal centrelines, road centrelines, land use |
| `district.bangkok.go.th/SEDPortal/` | District GIS portal |
| `pumps.bangkok.go.th` | §D.1 |

**Canal network topology and road centrelines are the two layers to hunt for here.** Road centrelines matter more than they sound: combined with the 1 m DTM they give the *road surface elevation* the supervisor's formula needs, without waiting for anyone.

## D.6 Prioritised request list for the BMA meeting

| # | Ask | Effort for BMA | What it unlocks |
|---|---|---|---|
| 1 | Permission + API for `pumps.bangkok.go.th` | Low — it is already published | Live operation; pump-station coordinates |
| 2 | Sensor coordinates, datum, install height, install date for all 568 sensors | Low — likely an existing asset register | Local water/flow features; a real map; the depth formula |
| 3 | TMD gridded radar, archive + live | Medium — inter-agency | The largest expected accuracy gain |
| 4 | Canal network topology (GIS, with gates and direction) | Medium — likely exists in DDS GIS | Upstream features; graph models later |
| 5 | Pump and gate operation logs | Medium — SCADA extraction | Removes a hidden control input |
| 6 | Confirmation of the `rf5min` 30 mm ceiling and the `rf24hr` 762 mm outlier | Low — a question, not a dataset | Data trust |
| 7 | 2026 data | Low — file transfer | A genuinely sealed test set |
| 8 | Historical Traffy Fondue flood reports (via NECTEC) | Low | Independent ground truth |

---

# PART E — THE ARCHITECTURE

## E.1 Design principles

1. **One source of truth for every constant.** Thresholds, horizons, split years, station exclusions live in `config/config.yaml` and nowhere else. If a number appears twice in the codebase, one of them is already wrong.
2. **Every caveat is a field in the API response, not a footnote.** `degraded`, `coord_quality`, `has_data`, `cap_status`, `sensors_offline`. A caveat that lives only in a PDF may as well not exist.
3. **Baselines first.** Persistence and climatology are computed and recorded *before* any model is trained, so every later number has a bar next to it.
4. **Chronological splits only, forever.** Neighbouring five-minute rows are near-identical; a random split inflates scores by 20–30 points and is indefensible.
5. **Nothing is promoted without a pre-registered rule.** The rule is written in `config.yaml` before the challenger model is trained.
6. **Notebooks own the data and ML work.** Per project convention, all analysis and training is `.ipynb`.

## E.2 Repository layout

```
bkk-flood-forecast/
├── config/
│   └── config.yaml              ← the ONLY place constants live
├── data/                        ← untouched raw + generated artefacts
│   ├── Rain_2019-2025/  Water_2019-2025/  Flow_2019-2025/  Flood_2019-2025/
│   ├── DTM_1M/  output_SRTMGL1.tif
│   ├── gis/                     ← boundaries, station registry, derived terrain
│   ├── interim/                 ← per-year Parquet, one file per dataset-year
│   ├── features/                ← model-ready feature tables
│   └── external/                ← Open-Meteo, Traffy, ThaiWater pulls
├── notebooks/                   ← ALL analysis and ML (.ipynb)
│   ├── 00_data_inventory.ipynb
│   ├── 01_ingest_to_parquet.ipynb
│   ├── 02_quality_and_events.ipynb
│   ├── 03_terrain_from_dtm.ipynb
│   ├── 04_external_data.ipynb
│   ├── 05_features.ipynb
│   ├── 06_baselines.ipynb
│   ├── 07_train_lightgbm.ipynb
│   ├── 08_train_onset.ipynb
│   ├── 09_train_depth_quantiles.ipynb
│   ├── 10_train_sequence.ipynb
│   ├── 11_evaluate.ipynb
│   ├── 12_calibrate.ipynb
│   └── 13_error_analysis.ipynb
├── src/bkkflood/                ← thin shared library (see note below)
├── backend/                     ← FastAPI service
├── frontend/                    ← React + Vite + Leaflet
├── db/                          ← PostgreSQL + PostGIS schema and loaders
├── models/                      ← trained artefacts + metadata
└── docs/
```

> **Note on the `.ipynb` rule.** All data work, feature engineering, training, evaluation and error analysis are notebooks, as required. Three things cannot be notebooks and are the only `.py`/`.jsx` in the project: the **FastAPI service** (a web server must be an importable module), the **React frontend**, and a **small shared library** `src/bkkflood/` holding functions the notebooks import (loading, feature builders, event detection) so that identical logic is not copy-pasted across 14 notebooks. If you would rather the library be inlined into the notebooks too, say so and it will be — but the same code will then exist in several places, which is how training and serving quietly drift apart. **This is a decision for you.**

## E.3 `config.yaml` — the contract

```yaml
version: "3.0.0"
data:
  years: [2019, 2020, 2021, 2022, 2023, 2024, 2025]
  cadence_minutes: 5
  model_cadence_minutes: 15        # resample to 15 min for modelling
  encoding: "utf-8-sig"
  null_token: "NULL"

exclusions:
  flow_stations: ["FW.PKG.01", "FW.LPW.01"]   # river scale, not canal
  dead_sensors:  ["FW.SSM.01"]                # flat zero for 7 years
  water_columns: ["wl_out02"]                 # 99.6% null
  rain_range_checks:
    rf5min:  {max: 25.0}      # 30.0 looks like a device ceiling — confirm with BMA
    rf1hr:   {max: 150.0}
    rf24hr:  {max: 400.0}     # nulls the 762 mm RF.BKY.02 outlier

flood_event:
  tiers_cm: {nuisance: 5, advisory: 15, severe: 30}
  primary_tier_cm: 15
  persistence_readings: 2       # ≥10 minutes
  merge_gap_minutes: 60
  min_event_minutes: 10

horizons_hours: [1, 3, 6]

splits:
  scheme: rolling_origin
  embargo_hours: 24
  folds:
    - {train: [2019, 2020],                   val: 2021, test: 2022}
    - {train: [2019, 2020, 2021],             val: 2022, test: 2023}
    - {train: [2019, 2020, 2021, 2022],       val: 2023, test: 2024}
    - {train: [2019, 2020, 2021, 2022, 2023], val: 2024, test: 2025}
  sealed_holdout: null            # set to 2026 when the data arrives

objective:
  primary_metric: f2              # recall weighted 2× — a miss costs more than a patrol
  max_miss_rate: 0.50
  promotion_rule:
    challenger_beats_lightgbm_by: 0.01   # absolute PR-AUC
    at_horizons: [3, 6]
    on_tier_cm: 15
    ties_go_to: lightgbm

alerting:
  cap_status: "Test"              # NEVER "Actual" without written BMA authorisation
  warning_p95_depth_cm: {1: 30, 3: 26, 6: 24}
```

## E.4 The pipeline

```
28 raw CSVs (54.8 GB)
   │  notebook 01 — chunked read, utf-8-sig, NULL→NaN, typed columns
   ▼
data/interim/{dataset}_{year}.parquet     (one file per dataset-year, ~250 MB total)
   │  notebook 02 — quality scorecard, range checks, event detection
   ▼
data/interim/quality_scorecard.parquet + flood_events.parquet
   │  notebook 03 — 1 m DTM → per-district and per-station terrain
   │  notebook 04 — Open-Meteo, Traffy Fondue, ThaiWater pulls
   │  notebook 05 — resample to 15 min, build features, build labels
   ▼
data/features/{year}.parquet              (model-ready, ~70 MB/year)
   │  notebooks 06–10 — baselines, LightGBM, onset, quantiles, sequence
   ▼
models/*.pkl + models/metadata.json
   │  notebooks 11–13 — evaluation, calibration, error analysis
   ▼
docs/reports/*.csv  →  FastAPI  →  PostgreSQL/PostGIS  →  React/Leaflet  →  CAP
```

**Memory discipline.** The full archive does not fit in RAM. Ingestion is chunked per station-year; nothing ever loads more than one dataset-year at a time. Verified feasible: the entire 54.8 GB was scanned in under six minutes using a streaming SQL engine with a 2 GB memory cap.

**Why 15-minute modelling cadence.** Five-minute rows are so autocorrelated that they triple the row count without adding information, and 15 minutes is still far finer than the 1-hour minimum forecast horizon. Labels are built from the **5-minute** data (so a 15-minute event is not lost) and features are sampled at 15 minutes.

## E.5 Feature specification

Grouped by what they represent. `NaN` is meaningful and is preserved — LightGBM handles it natively; sequence models get an imputed value plus a `_missing` indicator column.

**Flood autoregressive** (the station's own recent history)
`fl_depth_now`, `fl_depth_lag_1h`, `fl_depth_lag_3h`, `fl_rise_15min`, `fl_rise_1h`, `fl_max_3h`, `fl_max_24h`, `fl_mean_1h`, **`fl_std_3h`**, `fl_hours_since_5cm`, `fl_hours_since_15cm`, `fl_missing_share_3h`

> `fl_std_3h` — the variability of depth over the last three hours — was the strongest single feature in the previous version's 15 cm / 1 h model (68.9% of gain), well ahead of the current depth level (1.6%). *Recent instability predicts flooding better than the current level does.* That is the difference between a forecaster and a monitor, and it should be treated as a headline finding rather than a footnote.

**Rainfall, joined per district** (covers 33/33 flood districts)
`rain_rf1hr_mean/max`, `rain_rf3hr_mean/max`, `rain_rf6hr_mean`, `rain_rf24hr_mean`, `rain_rf1hr_delta1h`, `rain_rf1hr_delta3h`, `rain_spread` (max − mean across gauges in the district), `rain_antecedent_ratio` (24 h ÷ 72 h), `rain_gauges_reporting`

**Rainfall forecast, from Open-Meteo** `rain_fcst_1h`, `rain_fcst_3h`, `rain_fcst_6h`

> **The leakage trap, resolved in Phase 2.** Open-Meteo publishes *two* rainfall archives that return identical fields in an identical shape. `historical-forecast-api` is what the model **predicted** at the time — safe as a forecast feature. `archive-api` (ERA5) is what **actually fell**, reconstructed later from observations that did not exist at forecast time — safe as past rain, never as a forecast. Using ERA5 as `rain_fcst_*` trains the model on the answer sheet; in production it would receive a real forecast instead and accuracy would collapse silently. Phase 2 enforces the split with two functions, two files and two column prefixes (`fcst_*` vs `era5_*`). See `src/bkkflood/external.py`.

> **NOTE — The serving integration trap.** If the model is trained with forecast-rain features, the serving layer *must* supply them. If it does not, the model silently receives `NaN` for its most useful long-range input and quietly degrades to climatology, with no error raised anywhere. A startup assertion comparing `features.json` against what the serving layer can actually produce is mandatory.

**Water, citywide until coordinates arrive** `water_rise_1h_mean/max`, `water_rise_3h_mean`, `water_rising_share`, `water_offline_share`

**Flow, citywide, 27 usable stations** `flow_mean`, `flow_velocity_mean`, `flow_negative_share` (backflow), `flow_offline_share`

**Terrain, from the 1 m DTM — new in v3** `elev_m`, `slope_deg`, `depression_depth_m` (depth below the local sink-filled surface — literally "how much of a dip is this"), `elev_rank_in_district`, `dist_to_water_km`, `twi` (topographic wetness index)
> Previous versions tested terrain from the 31 m SRTM and found every correlation below 0.08. That test does not settle the question — a 31 m pixel averages away the 20–50 cm road dips where urban water collects. **Retest at 1 m before concluding terrain is uninformative.**

> **Phase 1 build notes.** Bangkok has about four metres of relief city-wide and a median ground level near 1 m. In terrain that flat, slope is nearly meaningless and **`depression_depth_m` is the headline feature** — it is measured in centimetres, the same units as the thing being predicted. Local features (elevation, slope, depression depth) are computed at the full 1 m district by district; routing features (flow accumulation, TWI) are non-local and run city-wide at 10 m. TWI is the weakest of the set and is labelled as such: it describes where water would pool on bare ground, and Bangkok's water goes into an engineered pipe-and-canal network built specifically to override the surface.

> **Two of these are not produced yet, and the reason is data.** `elev_m` and the rest are delivered **per district, not per station** — every coordinate in `station_registry_full.csv` is a district centroid, so all 107 flood sensors in a district share one point and sampling a 1 m raster there would return an identical number for each of them. That would look like a per-station feature and be a fabrication. `terrain.sample_points()` is written, tested and gated on `coord_quality`; the day BMA sends the coordinate spreadsheet, Phase 1 is a re-run rather than a rewrite. `dist_to_water_km` needs a canal layer (§D.6 request #3) — the shortcut of treating the DTM's nodata as water is false, since the nodata is simply everything outside the BMA boundary.

**Calendar and tide** `hour_sin/cos`, `doy_sin/cos`, `is_monsoon`, `tide_m2_sin/cos` (M2 = 12.42 h), `tide_spring_neap` (29.53 d)
> These give tidal *phase*, not height. Real physics, but half the story. Labelled clearly in the feature dictionary so nobody later mistakes them for measurements.

**Interaction** `rain_x_recent_flood`, `rain_x_depression_depth`

**Station identity** `station_code` as a categorical.
> Handle with care. In the previous version, station identity was ~39% of gain at the 6-hour horizon — meaning the model was largely saying *"this place floods often"*. That is climatology, not meteorology, and it is worth having, but it must be described honestly and it gives nothing for a newly installed sensor.

## E.6 Model strategy — and why

**The constraint that decides everything: 999 events at 15 cm, 179 at 30 cm, over seven years.**

| Family | Verdict | Reasoning |
|---|---|---|
| **Persistence & climatology baselines** | **Build first, always** | Persistence ("still flooded in an hour") is strong at 1 h and decays fast. That decay curve is the entire space a real model has to work in. |
| **LightGBM — the workhorse** | **Primary model** | Native `NaN` handling (we have 5–16% missingness), works with a few hundred positives, native categoricals, trains in minutes so many honest experiments are affordable, and gives feature attributions you can defend in a meeting. |
| **Onset specialists — LightGBM trained only on dry rows** | **Essential, not optional** | This is the most important modelling decision in the project. See below. |
| **Quantile regression (LightGBM, pinball loss)** | **For depth + P95** | The supervisor's scheme makes **P95 the headline number on two charts**. It is not an optional uncertainty band, it is the primary line. Every tier also gets a depth-derived path, because the 30 cm classifier has only 179 events and will never train reliably, whereas a quantile regressor learns from every row. |
| **GRU / TCN sequence models** | **Challenger, pre-registered** | Worth one honest attempt. In the previous round a GRU lost by 0.0003 — a rounding error — but was dramatically better on the severe tier. Promote only under the `config.yaml` rule. |
| **Transformer / Temporal Fusion Transformer** | **Do not attempt yet** | TFT has tens of thousands of parameters and needs thousands of events. With 999 it will memorise. Revisit if radar data arrives *and* several more years accumulate. |
| **Graph Neural Network** | **Blocked on data** | The natural model class for a flow network, and genuinely the right long-term answer — but a GNN without real canal topology is an architecture in search of a problem. Revisit when D.6 item 4 lands. |
| **Physical / hydrodynamic model (SWMM, HEC-RAS)** | **Out of scope, worth naming** | Would need pipe diameters, invert levels, pump curves. Mentioning that it was considered and why it was rejected strengthens the case with hydrologists at BMA. |

### The onset problem — read this before believing any recall number

A row where the station is **already** at or above the tier is *ongoing*. A row where it is **below** is *onset*. Only onset rows require forecasting at all — the ongoing ones are answered perfectly by a one-line persistence rule.

In the previous version, a headline recall of 55% decomposed into ~100% on already-flooded rows and **9% on genuine onsets**. The system was a monitoring tool wearing a forecasting label. Training a separate model on dry rows only — removing the shortcut so the model must learn precursors — took 1-hour onset recall from 9% to 63%.

**Mandatory in v3:**

- Every recall figure is reported **twice**: overall, and onset-only. A single number is not acceptable.
- Onset models are trained separately per tier and horizon.
- Onset precision was ~1–2% against a 0.01% base rate. That is a 40× lift — enough to raise a **Watch**, never enough to raise a **Warning**. The alert ladder (§E.10) is designed around the measured number, not the desired one.

### Handling the imbalance

- **Negative downsampling** (keep ~5% of negatives). Class weights of ~5,000 saturate the probabilities and cause early stopping after a handful of trees.
- **Isotonic calibration on validation data** to map scores back to real probabilities. Non-negotiable: the dashboard displays "68% risk" to a duty officer, and if rows predicted at 68% flood 4% of the time, that display is lying and no disclaimer fixes it.
- **Threshold selection on a dense grid in the upper tail.** In the previous round, evenly spaced rank quantiles put the top two candidates at the 99.5th percentile and the maximum with nothing between, so at a base rate near 1 in 11,000 every feasible operating point was invisible to the search. Precision came out at 0.05 instead of 0.60. **A uniform quantile grid is a bug at these base rates.**

## E.7 The cold-start problem

Eight flood stations and 45 water stations appear part-way through the archive, and more will be installed. A model leaning on `station_code` has nothing to say about them.

**Mitigation:** ensure the terrain features (§E.5) are strong enough to substitute. `depression_depth_m` from the 1 m DTM is the natural candidate: it gives a *physical* reason a site floods rather than the statistical fact that it has. Explicitly evaluate a "new station" scenario — hold out entire stations, not just time periods — and report that number separately.

## E.8 Evaluation protocol

**Rolling origin, chronological, never shuffled**, exactly as in `config.yaml` §E.3, with a 24-hour embargo at each year boundary (a label at 23:00 on 31 December looks six hours into the next year).

Thresholds are chosen on the **validation** year and frozen before the test year is touched.

**Metrics, reported for every tier × horizon:**

| Metric | Why |
|---|---|
| Precision | Of the alarms raised, how many were real |
| Recall — **overall and onset-only** | Of the real floods, how many we caught |
| F1, **F2** | F2 weights recall 2×; it is the objective in `config.yaml` |
| **Miss rate (FNR)** | "We miss 45% of floods" is the same fact as "recall 0.55" and lands very differently with a duty officer |
| PR-AUC | Threshold-free ranking quality — the right curve under extreme imbalance |
| Alarms per hit | The number operators actually complain about |
| **Event POD and median lead time, together** | Event POD of 0.99 with a median lead time of 0 minutes describes *detection*, not *warning*. Neither number may be quoted without the other. |
| **Quantile coverage** | The fraction of outcomes inside P05–P95, target 90%. A previous run hit 99.6–99.9% — bands so wide they were meaningless. **Coverage is an acceptance criterion, not a diagnostic.** |
| Reliability / calibration curve | Points below the diagonal = overstating danger; above = understating. Understating is the worse failure. |

**Accuracy appears nowhere.** A model that always says "no flood" scores 99.98%.

**Report the spread, not the mean.** Recall at 15 cm / 1 h ranged 0.39–0.66 across four test years. A single number hides that a bad year looks nothing like a good one, and an operator planning staffing needs to know.

**Two additional slices required in v3:**

1. **Held-out stations** (cold start, §E.7).
2. **Data-quality stratification** — performance on station-years with <5% missing vs >20% missing. Given the degradation in §B.3 this may explain much of the year-to-year variance, and nobody has checked.

## E.9 Error analysis — the most valuable hour in the project

Sort every miss into two buckets:

1. **Rain was falling and we still missed it.** A model problem. Worth working on.
2. **No rain recorded anywhere and the water arrived regardless.** Not a model problem — the rain fell between gauges, or the water came from an upstream canal, a pump switching off, or a blocked drain. No tuning fixes this bucket.

**This split converts the evaluation into a data request**, which is exactly what the BMA meeting needs.

In the previous run, nine of the ten worst misses had essentially no rain recorded nearby. One (13 November 2025, five stations within 30 minutes) had gauge rainfall of 0.0 but a **forecast** rain of 15.9 mm — the weather model knew rain was coming and the flood model scored ~1e-11. That one is bucket 1 and is actionable with data we already have.

Also required:

- **Concentration:** in the previous run the top 10 stations produced 47% of all misses. That turns "we miss 45% of flood rows" into a short list of specific sites to inspect physically.
- **Noisy stations:** a station with many false alarms and almost no real events is usually a faulty sensor, not a modelling problem. Check the quality scorecard before touching the model.
- **False positives from persistence:** if served scores are `max(model, persistence)`, the loudest false alarms will be rows where the road *is* flooded now but drains within the hour. That is a labelling consequence of forecasting, not a model error, and should be stated plainly before anyone tunes it away.

## E.10 Alert policy

| Level | Raised by | Rationale |
|---|---|---|
| **Watch** | 5 cm classifier, or any onset model | Onset precision ~1–2%. Fine for "check this", unacceptable for "close the road". **A Watch never auto-escalates.** |
| **Advisory** | 15 cm classifier above its frozen threshold | The primary tier |
| **Warning** | P95 predicted depth ≥ 30 / 26 / 24 cm at 1 / 3 / 6 h, **or** current depth ≥ 30 cm | Uses the depth regressor, not the 30 cm classifier — 179 events is not enough to train a classifier |
| **Critical** | Observed depth ≥ 30 cm now | Observation, not prediction |

**Why the Warning threshold falls with horizon.** The predicted band widens as the forecast reaches further out. Holding the trigger at 30 cm would make long-range warnings vanish — not because the risk fell, but because the uncertainty grew.

**Hybrid serving score:** `max(model, persistence)`. Persistence is perfect on already-flooded rows and useless elsewhere; the model is the opposite. Taking the maximum keeps the easy wins, never lowers recall, and is trivial to explain to an operator — which matters more here than elegance.

## E.11 CAP generation

Verified against the supervisor's CAP 1.2 JSON schema (OASIS, via `sri-alert.kku.ac.th`).

Required `alert` fields: `identifier`, `sender`, `sent`, `status`, `msgType`, `scope`.
Required `info` fields: `category`, `event`, `urgency`, `severity`, `certainty`.

**Mapping from our model output to CAP, and to the DDPM Thai alert levels:**

| Our level | DDPM | `urgency` | `severity` | `certainty` | `responseType` |
|---|---|---|---|---|---|
| Watch | เฝ้าระวัง (Fao Rawang) | `Future` (6 h) / `Expected` (3 h) | `Minor` | `Possible` | `Monitor` |
| Advisory | แจ้งเตือน (Chaeng Tuean) | `Expected` | `Moderate` | `Likely` | `Prepare` |
| Warning | เตือนภัย (Tuean Phai) | `Immediate` (1 h) / `Expected` (3–6 h) | `Severe` | `Likely` | `Avoid` |
| Critical (observed) | เตือนภัย (Tuean Phai) | `Immediate` | `Severe` / `Extreme` (≥50 cm) | `Observed` | `Avoid` / `Execute` |

**`urgency` is driven directly by the forecast horizon**, which is exactly what the CAP definitions call for: `Immediate` = within 1 hour, `Expected` = 1–12 hours, `Future` = over 12 hours.

Other rules:

- `category`: `["Met", "Geo"]`
- `scope`: `Public` once authorised; `Restricted` while internal
- `status`: **`Test` until BMA authorises in writing.** Config-gated, requires a deliberate change, logged.
- `effective` / `onset` / `expires`: onset = predicted threshold-crossing time; expires = onset + 3 h, refreshed each cycle
- `area`: `<geocode>` with the district code + `<polygon>` of the district boundary. **No fake circles.**
- Bilingual: two `info` blocks, `language: "th-TH"` and `"en-US"`
- Every alert is persisted with the model version, feature-set hash and input snapshot that produced it. When someone asks "why did you send this", the answer must be reconstructible.

## E.12 Backend — FastAPI contract

```
GET  /health
GET  /meta                         → model version, feature hash, data freshness, cap_status

GET  /stations                     → all sensors + coord_quality + has_data
GET  /stations/{code}/series       ?from&to&var
GET  /districts                    → GeoJSON + current status

GET  /now/summary                  → Panel 1: situation summary
GET  /now/flood                    → Panel 2: observed flood by station and district
GET  /now/rain                     → district rainfall
GET  /now/water                    → canal levels + rising share
GET  /now/flow                     → discharge + backflow share

GET  /forecast/risk                ?district|station&horizon=1,3,6
GET  /forecast/depth               ?district|station  → P05/P50/P95 + KPI chips
GET  /forecast/timeline            ?district          → Panel 4 + Panel 10 series

GET  /risk/hotspots                ?window=24h&limit=20
GET  /trends/events                ?tier&from&to&groupby=month|station|district

GET  /alerts                       → active alerts
GET  /alerts/{id}/cap.xml          → CAP 1.2 XML
GET  /alerts/{id}/cap.json         → CAP 1.2 JSON

POST /replay                       → set the system clock to a historical timestamp
```

**Every response carries an honesty envelope:**

```json
{
  "data": {},
  "meta": {
    "generated_at": "2026-08-07T14:05:00+07:00",
    "model_version": "3.0.0",
    "mode": "replay",
    "degraded": false,
    "degraded_reason": null,
    "sensors_offline_share": 0.11,
    "coord_quality": "district_centroid",
    "cap_status": "Test"
  }
}
```

**Replay mode is a first-class feature, not a demo hack.** It lets anyone step through the 2022 monsoon and watch what the system would have said, which is the single most persuasive thing to show at a BMA meeting — and it is honest, because it is clearly labelled `mode: replay`.

## E.13 Database — PostgreSQL + PostGIS

```sql
station(code PK, sensor_type, name_th, name_en,
        district, subdistrict, geom geometry(Point,4326),
        coord_quality, datum, install_height_m, first_seen, last_seen)

district(code PK, name_th, name_en, geom geometry(MultiPolygon,4326))

reading(station_code, ts, var, value, quality_flag)     -- partitioned by month
        PRIMARY KEY (station_code, ts, var)

flood_event(id PK, station_code, tier_cm, started_at, ended_at,
            peak_depth_cm, duration_minutes)

forecast(id PK, station_code, issued_at, horizon_h, tier_cm,
         risk_prob, depth_p05, depth_p50, depth_p95,
         model_version, feature_hash)

alert(id PK, district_code, level, issued_at, expires_at,
      cap_xml, cap_status, forecast_id FK, acknowledged_by, acknowledged_at)

quality(station_code, year, rows, null_pct, flagged, sensor_out)
```

Indexes: BRIN on `reading(ts)`, GiST on every `geom`, B-tree on `forecast(issued_at, station_code)`.

**Honest note on scale.** 393 million readings in `reading` is a large table for a laptop Postgres. Two options: (a) keep only a **rolling 90-day window** live and serve history from Parquet — recommended; or (b) use TimescaleDB compression. Do not silently load 393 M rows and discover the problem in a demo.

## E.14 Frontend — React + Vite + Leaflet

| Panel | Endpoint | Notes |
|---|---|---|
| Situation summary | `/now/summary` | Threshold-exceeding stations first |
| Observed flood map | `/now/flood`, `/districts` | District choropleth + station markers. Centroid-derived markers rendered **dashed**, with a tooltip explaining why |
| Forecast risk map | `/forecast/risk` | District choropleth only. No interpolated surface. |
| Risk chart | `/forecast/timeline` | P95 primary line, area-weighted mean secondary, alert-level background bands, KPI chips |
| Depth chart | `/forecast/depth` | 5/15/30 cm threshold lines, uncertainty band **only if coverage passed** |
| Water levels | `/now/water` | Canal levels as *changes* and percentiles, never absolute, until the datum is known |
| Rainfall | `/now/rain` | District bars + station table |
| Flow | `/now/flow` | Backflow highlighted |
| Hotspots | `/risk/hotspots` | Ranked list + risk timeline |
| Trends | `/trends/events` | Year, month, station, district |
| Alerts | `/alerts` | CAP XML/JSON viewer with a permanent `Test` banner while `cap_status != "Actual"` |
| Replay | `POST /replay` | Time slider across 2019–2025 |

**A global data-quality strip** is always visible: number of sensors reporting, share offline, data age, model version, and `Test` mode. It is not dismissible.

## E.15 Deployment, monitoring, retraining

- Docker Compose: `postgres+postgis`, `api`, `web`, `scheduler`.
- Scheduler: pull external data → build features → run models → write forecasts → evaluate alert rules → persist CAP.
- **Monitor the monitor:** alert on sensor dropout above a threshold, forecasts going stale, feature distributions drifting, and — most importantly — **feature-set mismatch between training and serving** (§E.5).
- Retrain annually at minimum. The sensor network changes every year.
- Every model artefact ships with `metadata.json`: training years, feature hash, config hash, metrics, git commit.

---

# PART F — DELIVERY

## F.1 Phased plan

| Phase | Work | Done when |
|---|---|---|
| **0 — Foundation** ✅ **DONE** | `config.yaml`; ingest all 28 CSVs to Parquet; quality scorecard; event detection; **notebooks 00–02** | Done. 51.1 GiB → 1.12 GiB Parquet, 3,736 station-years scored, event definition stress-tested. Five Part B figures corrected; see `docs/reports/phase0_verification.md`. |
| **1 — Terrain unlock** ⏳ **BUILT, NOT YET RUN** | Process the 1 m DTM: sink-fill, depression depth, slope, flow accumulation, TWI; **notebook 03** + `src/bkkflood/terrain.py` + `tests/test_terrain.py` | Code complete and unit-tested. Run `notebooks/03` (40–90 min). **Per-station sampling is written but deliberately blocked** — every coordinate we hold is a district centroid, so it would fabricate a feature. `dist_to_water_km` is blocked on a canal layer. Both unblock on a data request, not on effort. |
| **2 — External data** ⏳ **BUILT, NOT YET RUN** | Open-Meteo archived-forecast + ERA5; Traffy Fondue pull; ThaiWater investigation; **notebook 04** | Code and config complete. Run `notebooks/04` to fetch. Sources and the ask-list for BMA are in `docs/reports/phase2/external_sources.md`. |
| **3 — Features & baselines** (1 wk) | Resample to 15 min; full feature table; persistence and climatology; **notebooks 05–06** | Baseline numbers recorded *before* any model is trained |
| **4 — Models** (2 wks) | LightGBM per tier × horizon; onset specialists; depth quantiles; **notebooks 07–09** | All 9 tier×horizon combinations trained, thresholds frozen on validation |
| **5 — Honest evaluation** (1 wk) | Rolling origin; onset/ongoing split; cold-start slice; data-quality slice; calibration; error buckets; **notebooks 11–13** | `docs/reports/` regenerated end to end |
| **6 — Sequence challenger** (1 wk) | GRU/TCN under the pre-registered rule; **notebook 10** | Verdict, margin, and *where the loser won* all recorded |
| **7 — Backend** (2 wks) | FastAPI, all endpoints, honesty envelope, replay | OpenAPI docs complete; replay steps through 2022 |
| **8 — Frontend** (2 wks) | React + Leaflet, all 11 panels, quality strip | Every panel served by a real endpoint |
| **9 — Database & deploy** (1 wk) | PostGIS schema, loaders, rolling window, Docker Compose | `docker compose up` produces a working system |
| **10 — CAP & BMA pack** (1 wk) | CAP generator, DDPM mapping, meeting materials | Valid CAP XML/JSON in `Test`; agenda from §D.6 |

**≈ 14 weeks.** Phases 1 and 2 are new to v3 and unlock things previous versions assumed were blocked.

## F.2 Acceptance criteria

The system is not "done" until:

1. Every number in the model report regenerates from a notebook with one command.
2. Recall is reported **twice** (overall and onset-only) for every tier × horizon.
3. Event POD is never printed without median lead time beside it.
4. Depth quantile coverage is within 85–93% (target 90%) or the band is not displayed.
5. Calibration curves exist and are within tolerance.
6. A cold-start (held-out-station) evaluation exists.
7. `cap_status` is `Test` and changing it requires editing a config file.
8. The frontend renders a caveat for every approximation, driven by an API field.
9. The 2025 test year is described as **reused**, not sealed, until 2026 data arrives.

## F.3 Risks

| Risk | Consequence | Mitigation |
|---|---|---|
| No live feed materialises | System stays a demo | Pursue `pumps.bangkok.go.th` permission first — it exists already, which makes it a far easier ask than a new API |
| Radar rainfall unavailable | Onset detection stays capped | Gauge IDW + Open-Meteo forecast rain; expect less; say so |
| Sensor network keeps degrading | Silent accuracy loss | `*_offline_share` features; quality scorecard per station-year; offline share on the dashboard |
| Feature drift between training and serving | Silent accuracy loss, no error | `features.json` version-controlled and asserted at load |
| Alert fatigue from onset Watches | Operators stop reading | Watch never escalates; measured precision published on the dashboard |
| `cap_status` flipped to `Actual` prematurely | Real public alerts from an experimental model | Config-gated, logged, requires named authorisation |
| 1 m DTM processing overruns | Phase 1 slips | 13.9 GB with built-in overviews; process per district tile, not whole-raster |
| Scraping a government site without asking | Damages the BMA relationship | **Ask first. Always.** |

## F.4 Open questions for you and the supervisor

1. ~~**The `.ipynb` rule and the shared library** (§E.2)~~ — **resolved 8 Aug 2026: a thin `src/bkkflood/` is allowed.** Notebooks remain where all work happens; they import shared functions so the flood-event definition exists exactly once.
2. **Does BMA permit programmatic access to `pumps.bangkok.go.th`?** Highest-leverage question in the project.
3. **What is the `wl_in` datum?**
4. ~~**Is `rf5min = 30.0` a real ceiling or a device limit?**~~ — **answered from the data: neither.** One gauge of 131 reaches it. Worth a passing mention to BMA, not a data request.
5. **Is the RF.BKY.02 762 mm / 24 h reading real?** (Almost certainly not.)
6. **Is a continuous flood surface a hard requirement?** §C.2 argues it is not defensible; a decision is needed before the frontend is built.
7. **Who is the named owner who authorises `cap_status: Actual`?**
8. **What miss rate is acceptable to BMA, in writing, in advance?** "We miss roughly 45% of flood onsets at 1 hour" has to be agreed before the first miss, not after. A system whose limits are only discussed after a failure will not survive that failure.

## F.5 Fate of the existing `docs/` files

| File | Status |
|---|---|
| `technical_roadmap.md` | Superseded — Parts E and F replace it. Corrections in §B.9. |
| `model_report.md` | **Keep.** Its measured results are the only empirical evidence available and are cited throughout. Its v1/v2 numbers must be re-derived under v3. |
| `data_inventory.md` | Superseded by Part B (corrected station counts, added quality trend). |
| `data_requests.md` | Superseded by §D.6 — reordered, with the pumps portal added at the top. |
| `supervisor_reference_docs_review.md` | **Keep** — records confirmed decisions with the supervisor (Phrae deck is reference-only; soil moisture is illustrative). |
| `full_project_roadmap.md`, `dataset_research_report.md`, `ml_engineering_project_analysis.md`, `bma_meeting_pack.md` | Superseded. Safe to archive. |
| `BKK_Flood_Forecast_ML_Documentation.docx` | Superseded. |
| `sample_cap_alert.xml` | **Keep** as a fixture for the CAP generator's tests. |
| `reports/*.csv` | **Keep** — the previous evaluation outputs, useful as a v2-vs-v3 comparison. |
| `reports/phase0/*` | **New.** Everything notebooks 00–02 produce. |
| `reports/phase0_verification.md` | **New.** Part B checked line by line against the notebooks. |

Nothing has been deleted.

---

## Appendix — Provenance of every figure in Part B

| Figure | How obtained |
|---|---|
| Row counts, station counts, null rates, value ranges, per-station aggregates | Full DuckDB scan of all 28 CSVs, 7 Aug 2026, grouped by station and year. Output: `station_profile.json` |
| Flood event counts, durations, stations affected | Windowed run-length detection over all 7 flood CSVs at tiers 5/15/30 cm, ≥2 consecutive readings |
| Duplicate-key check | `count(*)` vs `count(DISTINCT timestamp)` per station-year — zero difference everywhere |
| DTM extent, CRS, resolution, overviews | `rasterio` metadata read + bounds reprojected to EPSG:4326 |
| Bangkok boundary extent | Coordinate walk over `bangkok_districts.geojson` |
| Prefix coverage (33/33, 13/33, 3/33) | Set intersection of district-code prefixes across the four datasets |
| Station registry confidence breakdown | `value_counts` over `station_registry_full.csv` |
| `pumps.bangkok.go.th` contents | Direct page fetch, 7 Aug 2026 |
| Traffy Fondue schema | Live GeoJSON API response, 7 Aug 2026 |
| Model performance figures | Carried from `docs/model_report.md`, always labelled as previous-version results |

**Sources**

- [OASIS CAP 1.2 schema (supervisor-provided PDF, sri-alert.kku.ac.th)](https://sri-alert.kku.ac.th/docs/CAP%20Standard/)
- [BMA Drainage & Sewerage pump portal](https://pumps.bangkok.go.th/)
- [Traffy Fondue public GeoJSON API](https://publicapi.traffy.in.th/teamchadchart-stat-api/geojson/v1)
- [ThaiWater API documentation](https://standard.thaiwater.net/glossary/api-documentation/)
- [TMD Bangkok radar — Nong Chok](https://weather.tmd.go.th/bma_nck.php) · [Nong Khaem](https://weather.tmd.go.th/bma_nkm.php)
- [Open Government Data of Bangkok — Traffy Fondue dataset](https://data.bangkok.go.th/en/dataset/traffy-fondue)
- [BMA City Planning GIS portal](https://cityplangis.bangkok.go.th/cpdPortal/)
