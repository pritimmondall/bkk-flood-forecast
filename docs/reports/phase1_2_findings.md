# Phases 1 and 2 — what the runs actually found

*8 August 2026. Written after `notebooks/03` and `notebooks/04` were run end to end.*

Two of the four headline results are not what was expected, and one of them
invalidates a feature the spec was counting on. This document records what
happened, what it means, and what to do next.

---

## 1. The 1 m DTM is not bare earth in dense districts — found, and fixed

**The most surprising finding in either phase. Not the most important one** — an
earlier draft of this document called it that, which overstated its impact.
Terrain does not appear in the top ten features of the previous version's model
at any horizon, and 76% of the onset signal is rainfall. This mattered for one
dashboard panel and for cold-starting new sensors, not for the forecaster.

**Status: fixed in Phase 1.5.** See the end of this section.

Notebook 03 reported median ground elevations that make no physical sense for
Bangkok:

| District | Median elevation | Character |
|---|---|---|
| Pathum Wan | **4.57 m** | dense inner city |
| Bang Rak | **4.55 m** | dense inner city |
| Ratchathewi | **4.69 m** | dense inner city |
| Lat Krabang | 0.63 m | open, agricultural |
| Phra Khanong | 0.41 m | outer, low-lying |

Bangkok's inner districts are not four metres higher than its outskirts. Central
Rattanakosin sits at roughly 1–2 m above mean sea level.

### What the raster actually contains

Reading three 800 × 800 m windows at full resolution settles it. Pathum Wan and
Bang Rak are **strongly bimodal** — a low mode around 2–3 m and an enormous
spike piled up just below 5 m — while Lat Krabang is a single believable
distribution around 0.8 m with canals at −0.5 m.

Visually the dense windows are covered in **smooth rounded domes** at roughly
roof height, with the street grid visible as low channels between them. That is
the classic signature of a DTM produced by removing building returns from a
surface model and interpolating across the holes: over a large building
footprint there is no ground to interpolate from, so the fill drifts up toward
roof level.

Two supporting details rule out the simpler explanations:

- **It is not clipped.** An early hypothesis, from a coarse overview read, was a
  hard 5 m ceiling. Checking at full resolution disproves it: the city maximum is
  **14.9 m** and only 0.02% of pixels sit above 4.98 m. The overview read had
  averaged 256 × 256 blocks and smoothed the extremes away. Hypothesis dropped.
- **It is not raw building returns.** The median step between neighbouring pixels
  in Pathum Wan is 1.9 cm and the 99th percentile is 48 cm. Real building walls
  would give metre-scale steps. The surface is smooth — interpolated, not
  measured.

### Why this contaminates the terrain features

`depression_depth_m` is computed against the surrounding surface. Where that
surface is an interpolated dome at roof height, a street is not a 30 cm road dip
— it is a 2 m canyon relative to a building.

The output shows exactly that, and the pattern is diagnostic:

| District | Median elevation | p95 depression depth |
|---|---|---|
| Pathum Wan | 4.57 m | **1.89 m** |
| Dusit | 4.49 m | **1.89 m** |
| Ratchathewi | 4.69 m | **1.88 m** |
| Phra Khanong | 0.41 m | 0.45 m |
| Suan Luang | 0.52 m | 0.38 m |

**The highest districts have the deepest depressions.** In a flat delta city that
is backwards, and it is precisely what building-height interpolation produces.
It also explains the 30% of city area reported as "sitting in a dip": much of
that is street, measured against rooftops.

### What this does to the retest

The Phase 1 headline — strongest |Spearman| of **0.231** against flood frequency
— has to be withdrawn as evidence either way.

| Feature | Spearman | p |
|---|---|---|
| mean wetness index | −0.231 | 0.196 |
| elevation of the low tenth | −0.215 | 0.229 |
| median slope | +0.213 | 0.234 |
| share of area in a dip | −0.210 | 0.241 |
| p99 depression depth | +0.153 | 0.395 |

**Nothing is significant** — every p-value is above 0.19 at n = 33 — and the
depression signs are inconsistent. The honest conclusion is not "terrain is
weak at 1 m". It is:

> The retest is **inconclusive**, because the raster is not bare earth in the
> districts that hold most of the flood sensors. The 31 m SRTM test was wrong for
> a resolution reason; this test is wrong for a data-content reason. Terrain has
> still not had a fair trial.

### FIXED — Phase 1.5

Implemented in `terrain.ground_mask()`, wired into `district_terrain()`, and
verified on real districts:

| District | | elevation p50 | depression p95 |
|---|---|---|---|
| Bang Rak | dense | 4.54 → **1.25 m** | 1.83 → **0.18 m** |
| Phra Khanong | open, control | 0.41 → **0.34 m** | 0.45 → **0.15 m** |

The contamination is one-sided — interpolated buildings sit *above* the real
surface, never below — so a rolling minimum over a window wider than a city
block, plus a tolerance, selects the surface water actually runs on. Bang Rak's
1.25 m is plausible for central Bangkok; the control barely moves, which is what
distinguishes a fix from a fudge.

The feature itself is the real win. Depression depth went from **1.83 vs 0.45**
(meaning different things in different districts) to **0.18 vs 0.15** (measuring
one thing everywhere), at the 20–50 cm scale the spec says urban water collects
in. Before the fix it was unusable as a model input; now it is comparable across
the city.

Six unit tests guard it, including a control that fails if the window grows wide
enough to start selecting canal beds instead of streets.

### Roads alone do not work — and that corrects something stated above

Option 1 in the list below says "the buildings only contaminate building
footprints, so sampling only on roads removes the problem entirely." **That is
wrong.** Measured on Bang Rak with 196,720 OSM road segments:

| Mask | elevation p50 | area kept |
|---|---|---|
| none | 4.54 m | 100% |
| **roads only**, 3 m buffer | **3.77 m** | 0.6% |
| roads only, 8 m buffer | 4.12 m | 1.1% |
| roads only, 15 m buffer | 4.31 m | 1.5% |
| ground only | 1.72 m | 9.4% |
| **roads AND ground** | **1.56 m** | 0.9% |

Even a 3 metre buffer around a road centreline sits at 3.77 m. The interpolated
fill does not stop at the building outline — it **bleeds across narrow streets**,
so a buffer around a centreline still lands on the shoulder of a dome. Masking to
roads without the local-minimum test barely helps.

**The combination is what works, and it is what the code now does.** Roads still
earn their place: they guarantee the surviving cells are on a road rather than in
a canal or a car park, which is exactly what
`Flood Depth = Water Level − Road Elevation` needs and what the ground mask alone
cannot tell apart. And the result is stable at 1.56–1.57 m across every buffer
from 3 to 15 m, which says it is not an artefact of an arbitrary parameter.

Full-district result with both masks: Bang Rak **1.37 m**, Phra Khanong
**0.28 m**, depression p95 **0.08 m** and **0.01 m**.

`scripts/fetch_osm_roads.py` fetches the roads. **It is optional** — the ground
mask alone already fixes the contamination, and notebook 03 falls back to it.

The first version of that script failed three ways in a row, and all three were
the same mistake — asking a free, shared, volunteer-run service for the whole
city at once, anonymously:

| Endpoint | Result | Cause |
|---|---|---|
| overpass-api.de | HTTP 406 | no `User-Agent`; Overpass refuses anonymous callers |
| kumi.systems | HTTP 429 | rate limited |
| overpass.osm.ch | 0 ways | one query over 60 x 50 km never completes |

It now identifies itself, splits the city into a 4x4 grid, pauses between tiles,
backs off on 429, saves after every tile so a partial failure keeps its progress,
excludes `service` roads by default (they are most of the volume and mostly
private driveways), and prints Overpass's own `remark` field, which is where it
explains why it refused.

**Still worth one email to BMA:** what is `DTM_1M` — bare earth or surface, what
filtering produced it, what vertical datum? That decides whether the mask is a
workaround or the permanent answer.

### The options considered, in order of cost

1. **Mask to road corridors.** ~~The buildings only contaminate building
   footprints. Sampling terrain only on roads removes the problem entirely~~
   — **measured and disproved, see above.** Roads help only in combination
   and delivers the "Road Elevation" the supervisor's formula
   `Flood Depth = Water Level − Road Elevation` actually asks for. OpenStreetMap
   road centrelines for Bangkok are free, openly licensed, and a few megabytes;
   buffer them 5–10 m and sample inside. **This is cheap and should be the next
   thing done** — call it Phase 1.5.
2. **Ask BMA what `DTM_1M` is.** Bare earth or surface? What filtering produced
   it? What vertical datum? This should join the data-request list — it is one
   email and it determines how much of the above is even necessary.
3. Fall back to the 31 m SRTM for dense districts. Not recommended: it trades a
   known contamination for a known blindness.

### What is still sound

Everything the notebook reports about **open districts** — Lat Krabang, Nong
Chok, Prawet, Phra Khanong — looks like genuine bare earth and is usable.
The pipeline itself is correct: tiling was exact (`depression_truncated_share`
is 0.0000 for all 50 districts), flow accumulation converged in 222 iterations
over 16.2 million cells, and DTM coverage is 100% for 49 of 50 districts.
The machinery is right. The input is not what it says on the label.

---

## 2. Archived forecast rain: fixed, then broken worse, now guarded

This one went wrong twice and the second time was mine.

### First failure — loud

`fcst_*` came back empty. Every year, including 2025, failed with `400 Bad
Request`, which rules out a coverage limit. The forecast call differed from the
working ERA5 call in one parameter: `models=ecmwf_ifs_hres`. The API is blunt
about it — *"Cannot initialize MultiDomains from invalid String value
ecmwf_ifs_hres"*. It was a name I invented. Not a valid slug.

### Second failure — silent, and much more dangerous

The fix was to set `model: null`, removing the parameter entirely. The pull then
returned **3,068,400 rows across all seven years** and looked completely healthy:
zero nulls, sensible rainfall means, full coverage.

It was ERA5.

| Year | Hours identical to ERA5 | Correlation |
|---|---|---|
| 2019 | **100.00%** | 1.0000 |
| 2020 | **100.00%** | 1.0000 |
| 2021 | **100.00%** | 1.0000 |
| 2022 | **100.00%** | 1.0000 |
| 2023 | **100.00%** | 1.0000 |
| 2024 | **100.00%** | 1.0000 |
| 2025 | **100.00%** | 1.0000 |

Without an explicit model, the historical-forecast endpoint serves archived
*analysis* for past dates rather than what the model predicted at the time. Two
different hosts, two different filenames, two different column prefixes, and
byte-for-byte the same rainfall.

**This is worse than the 400 error.** A 400 is loud and stops the pipeline. A
forecast column silently containing the observation is the answer sheet: it
would train beautifully, show `rain_fcst_3h` as a top feature, and collapse on
the first live day when a real forecast replaced it — with nothing in any log.
It is precisely the failure rule 7 exists to prevent, and the `fcst_` / `era5_`
prefix scheme did not catch it, because prefixes separate **names** and the
problem was **content**.

### Why the check missed it

The first diagnostic asked *"does the endpoint return data?"*. Every candidate
said yes, so `null` was chosen for its apparently full 2019–2025 coverage, and
this document confidently withdrew the coverage warning. Both conclusions rested
on the wrong question.

The right question is *"is it different from what actually fell?"* — a forecast
that equals the observation is not a forecast.

### Third failure — absence read as difference

The corrected diagnostic reported `ecmwf_ifs025` as a genuine forecast back to
2019, so it was pinned and re-pulled. The result: **3,068,400 rows, guard
passed, 2019–2025.**

It was 73% empty.

| Year | Rows | With a forecast value |
|---|---|---|
| 2019–2023 | 2,191,200 | **0** |
| 2024 | 439,200 | 387,200 (88%) |
| 2025 | 438,000 | 438,000 (100%) |
| **Usable** | | **825,200 of 3,068,400 — 26.9%** |

`ecmwf_ifs025`'s archive starts **2024-02-03**, exactly as Open-Meteo's
"Available Since" table said. The earlier years returned NaN — and NaN is not
equal to anything, so the identical-share test scored them 0.0% and read that as
"genuinely different from ERA5".

**Absence looked exactly like difference.** The same shape of mistake as the
first two, in the opposite direction: the first check confused "data arrived"
with "correct data", the second confused "not identical" with "not empty".

And the earlier claim in this document — that both ECMWF slugs "reach 2019,
better than the docs claim" — was wrong. The docs were right. Measuring beat
reading the documentation twice and lost to it once, because the measurement
had a hole in it.

### Resolved: the two archives are complementary, not competing

The three-state diagnostic finally gives a clean answer:

| Model | 2019 | 2021 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| `null` / `best_match` | reanalysis | reanalysis | reanalysis | reanalysis | reanalysis |
| `ecmwf_ifs04` | no data | no data | **forecast** | **forecast** | no data |
| `ecmwf_ifs025` | no data | no data | no data | **forecast** | **forecast** |

`ifs04` **stops** after early 2024 and `ifs025` **starts** there — ECMWF replaced
the 0.4° archive with 0.25° in February 2024. They are two halves of one series,
and the whole argument about which to pick was the wrong question.

**Listing both covers roughly 2022-11 → 2025**: about three of seven years,
against two for either alone. `config.yaml` now takes
`models: ["ecmwf_ifs04", "ecmwf_ifs025"]`, oldest archive first, and
`_fetch_openmeteo` splices them — later model wins where both have data, because
it is the finer grid.

The splice changes grid resolution from ~44 km to ~25 km part way through the
series. That is a genuine compromise. It is accepted because the change is
**known and dated**, unlike `best_match`, which swaps models underneath you with
no way to tell.

Also note the wet-hour agreement for the genuine models: **1.9%–4.3%**. A real
forecast almost never matches the observation to the decimal on a rainy hour.
That is what a working forecast feature looks like, and it is the number to
compare against if this is ever re-pulled.

### What has changed

1. **The guard now checks emptiness first.**
   `assert_forecast_is_not_reanalysis()` raises if any year has under 1%
   coverage, and reports coverage per year. It correctly failed the ifs025-only
   file: `2019:0% 2020:0% 2021:0% 2022:0% 2023:0% 2024:88% 2025:100%`.
2. **The diagnostic reports three states per year** — `NO DATA`, `REANALYSIS`,
   `real forecast`. Only the third counts.
3. **`config.external.open_meteo.forecast.models` is now a list**, and the
   fetcher splices archives.

### Before leaning on this feature, measure whether it is worth anything

Three rounds have gone into making `rain_fcst_*` real. None of them established
that it **helps**, and there is now reason to doubt it:

- §3 below measures the BMA gauges at **0.298** correlation with flooding
  against ERA5's **0.088**, because 25 km grids cannot see 2–5 km convective
  cells. The archived forecast is 25–44 km — the same coarseness or worse.
- The spec's claim that forecast rain correlates ~3× better with 6-hour flood
  labels than past gauge rain is carried over from v1/v2 and has never been
  re-tested on this data.
- Even spliced, it covers 3 of 7 years: absent from fold 1, partial in fold 2.

**Notebook 05 should run the value test on 2024–2025, where genuine forecast
data exists**, before deciding whether to carry the feature at all. If it adds
nothing over the BMA gauges, drop it — and the entire fold-inconsistency problem
disappears with it. That is a cheap experiment and it settles a question three
rounds of plumbing did not.

### The fold consequence — real, and now bounded

> Spliced coverage begins **late 2022**. In the four rolling-origin folds,
> `rain_fcst_*` is absent from fold 1, partial in fold 2, and present in folds 3
> and 4. Its measured importance will not be comparable across folds.
>
> **Notebook 05 must make this an explicit, recorded decision**, and it belongs
> in `config.yaml` beside the model list: restrict the feature to the folds that
> have it and report those separately, drop it on the evidence of the value test
> above, or keep it NaN-filled and state plainly that its importance is only
> measurable on later folds.

### Fourth and fifth failures — both mine, both in the splice

Implementing the splice broke two things that the row count did not reveal.

**The cache key.** I added the model name to the cache key, including a
`"default"` segment for the no-model ERA5 source. That renamed every existing
cache entry, orphaned 3 million already-fetched ERA5 rows, and forced a re-pull
that came back **two years short** — ERA5 dropped from 3,068,400 rows to
2,192,400, losing 2023 and 2025. The summary still printed a plausible-looking
number. *A cache key change is a data migration.* The key now includes the model
only when there is one, so the original files are found again and nothing is
re-fetched.

**The dedupe.** "Later model wins" is only correct where the later model has
data. `ecmwf_ifs04` covers 2023 in full; `ecmwf_ifs025` does not. Keeping the
last row per `(district, ts)` replaced 8,760 genuine hours per district with the
newer model's NaNs — the API had returned the data and the splice threw it away.
Empty rows are now dropped **per frame, before** concatenating and deduping.

### Verified result

Rebuilt from cache, no re-fetching:

| Year | Forecast rows with a value | Note |
|---|---|---|
| 2019–2021 | 0 | before either archive |
| 2022 | 63,350 | `ifs04` archive opens 2022-11-07 |
| 2023 | 438,000 | `ifs04`, full year |
| 2024 | 439,200 | `ifs04` to Feb, then `ifs025` |
| 2025 | 438,000 | `ifs025`, full year |
| **Total** | **1,378,550** | genuine archived forecast |

ERA5 is back to its full **3,068,400** rows across all seven years.

### What to run

```bash
pytest tests/ -q                        # 21 tests, one second
# re-run notebook 04
```

Nothing re-fetches — both sources rebuild from the existing cache. Expect
**1,378,550** usable forecast rows and **3,068,400** ERA5 rows. The guard checks
both failure modes: a reanalysis in disguise, and an empty file wearing the right
row count.

The orphaned `data/external/_cache/observed_default_*` files are harmless
duplicates and can be deleted.

---

## 2b. The supervisor's GFS suggestion — measured, and it wins

*Received 9 August 2026: use NOAA's GFS as a forecast rainfall input; it is
~0.25° (25–28 km) in Thailand and would need downscaling to reach 1 km.*

**Tested, and GFS replaces the ECMWF splice outright.** Results from
`scripts/diagnose_openmeteo.py`:

| Model | Genuine forecast years | Grid |
|---|---|---|
| **`gfs_seamless`** | **2021, 2022, 2023, 2024, 2025** | **0.11° (~13 km)** |
| `gfs_global` | identical to `gfs_seamless` | 0.11° |
| `ecmwf_ifs025` | 2024, 2025 | 0.25° (~25 km) |
| `ecmwf_ifs04` | 2023, 2024 | 0.4° (~44 km) |
| `null` / `best_match` | none — reanalysis in every year | — |

GFS covers **every year the ECMWF pair covers, plus 2021 and 2022, at a finer
grid than either.** So there is nothing left for ECMWF to contribute and no
reason to splice at all. `config` is now `models: ["gfs_seamless"]` — one model,
one resolution, 2021-03 to 2025, with no regime change part way through the
series. That is strictly better than the two-model splice it replaces, and
simpler.

`gfs_seamless` and `gfs_global` returned identical values in every probed year:
"seamless" blends GFS with HRRR, which is US-only, so outside North America it is
just the global model.

### A correction: I was wrong that GFS was "another 25 km product"

This document previously argued GFS could not help on resolution because it was
the same 25 km as ECMWF IFS. **That was wrong.** The supervisor's note quotes
NOAA's own 0.25° product, but Open-Meteo serves GFS *surface* variables at
**0.11°, roughly 13 km** — about twice as fine as ERA5 and ECMWF IFS 0.25.

That is a real improvement and it should be measured rather than dismissed. It
does not change the radar argument: 13 km is still 3–6× coarser than the 2–5 km
convective cells that cause this flooding, so TMD radar stays priority 1. But
whether 13 km forecast rain beats the BMA gauges is now a genuine open question
for notebook 05, not something to rule out in advance.

### The fold problem shrinks but does not vanish

GFS begins **2021-03-23**, so 2019 and 2020 stay empty — **5 of 7 years instead
of 3**. Fold 1 still trains on two years with no forecast rain at all, so
`rain_fcst_*` importance is not comparable across every fold. Notebook 05 still
has to make that an explicit, recorded decision; it is simply a smaller problem
than it was.

### On downscaling to 1 km — the technique does not transfer

The note comes from the Heatwave Early Warning project, where downscaling 25 km
to 1 km is standard and works well. **It works there because temperature is
strongly and predictably related to elevation, land cover and urban density** —
the fine structure is genuinely recoverable from static covariates.

Convective rainfall is not like that. Where a thunderstorm cell sits on a given
afternoon is not a function of terrain in a flat delta city. Downscaling would
redistribute the grid-cell average according to a static pattern, producing a map
that looks 1 km and carries no more information about *where* the rain fell. For
heat that is a real gain. For flash-flood rainfall it is a confident picture of
something we do not know, which is worse than an honest coarse number.

**Radar is what actually gives 1 km rainfall** — it measures where the cell is
rather than inferring it. Worth keeping that distinction explicit with the
supervisor: GFS improves the forecast feature and is a good catch; the
downscaling step should not be presented to BMA as a substitute for radar.

### A dependency worth recording

The splice rule in `external.py` said "the last entry wins because it is the
finer grid". That justification died the moment a 0.11° model joined a list whose
later entries were 0.25° and 0.4°. The rule is now documented as a **preference
order — most-preferred last** — which is what it always actually was.

### Result — verified 9 August 2026

`scripts/refresh_forecast.py` (seven calls, two minutes — the whole notebook did
not need re-running for a change to one file):

| Year | Rows with a forecast |
|---|---|
| 2019, 2020 | 0 — archive begins 2021-03-23 |
| 2021 | 340,400 |
| 2022 | 438,000 |
| 2023 | 438,000 |
| 2024 | 439,200 |
| 2025 | 438,000 |
| **Total** | **2,093,600** (was 1,378,550 from the ECMWF splice) |

**Guard passed**: 100% of rows usable, no contaminated years, no empty years.

| Year | identical (all) | identical (wet) | wet hours |
|---|---|---|---|
| 2021 | 61.1% | **2.6%** | 135,823 |
| 2022 | 65.3% | **2.5%** | 155,981 |
| 2023 | 71.7% | **2.1%** | 126,880 |
| 2024 | 69.6% | **2.4%** | 136,775 |
| 2025 | 69.4% | **2.5%** | 137,494 |

Wet-hour agreement of 2.1–2.6%, steady across five years, is what a genuine
forecast looks like: right about roughly *when* it rains, wrong about exactly
how much. Compare the contaminated file, which scored 100% on wet hours.

**A small confirmation worth noting.** 2021 returned 340,400 of a possible
438,000 rows — 77.7%, or about 284 days. That places the archive start at
approximately 22 March 2021, matching Open-Meteo's documented 2021-03-23 to
within a day. The data agrees with the documentation, which is a good sign for
both.

### One instruction that was wrong, and why

Earlier notes in this document said to `rm data/external/_cache/forecast_*`
before switching models. **Do not.** That was correct when the cache key was
`forecast_<year>_...`, and stopped being correct once the key started including
the model name — `forecast_gfs_seamless_2021_...` cannot collide with
`forecast_ecmwf_ifs04_2021_...`. Deleting would have discarded good ECMWF
responses and forced a needless re-fetch. The instruction was carried forward
from two changes earlier without rechecking whether it still applied.

---

## 3. ERA5 is a much weaker rainfall source than the BMA gauges

This one is a clean, useful result — and it is worth more than it looks.

| Source | Correlation with flooding | Mean rain on flood days | On other days | Ratio |
|---|---|---|---|---|
| **BMA gauges** | **0.298** | 50.2 mm | 3.7 mm | **13.6×** |
| ERA5 reanalysis | 0.088 | 14.5 mm | 4.6 mm | 3.2× |

On a district-day that flooded, the BMA gauges recorded **13.6 times** more rain
than on a day that did not. ERA5 managed 3.2 times.

The reason is resolution. ERA5 is ~25 km; Bangkok is about 40 km across, so the
whole city sits in two or three grid cells and every district gets almost the
same rainfall. Convective cells 2–5 km across — the ones that actually cause
this flooding — are invisible at that scale.

Two consequences:

- **ERA5 adds little as a past-rain feature.** We already hold 131 real gauges
  that are three times more discriminative. Keep ERA5 for gap-filling when
  gauges are offline (which matters more each year — flood-sensor nulls reach
  10.7% by 2025) and do not expect it to carry signal.
- **It is direct evidence for the radar request.** The spec ranks TMD radar as
  priority 1 on the argument that spatial resolution is the binding constraint.
  This is that argument, measured: coarsening rainfall from gauge scale to 25 km
  costs three quarters of the correlation with flooding. That number belongs in
  the BMA meeting.

ERA5 coverage itself is perfect — 100% of hours for all 50 districts across all
seven years, 3,068,400 rows.

---

## 4. Traffy Fondue found 10,123 flood reports where we have no sensor

The independent ground truth working exactly as intended.

**10,123 citizen flood reports came from districts with no flood sensor at all.**
Those floods are invisible to the model, and — more importantly — invisible to
every evaluation number this project has ever produced. Recall is measured
against sensor-derived labels, so a flood nobody's sensor saw was never counted
as a miss.

This does not change any model metric. It changes what the metrics *mean*, and
it is the strongest single argument for either more sensors or a report-based
label stream. It is also a very concrete thing to show BMA: their own citizens'
reports, from their own platform, in districts their own sensor network does not
cover.

---

## 5. What to do next, in order

| # | Action | Cost | Why |
|---|---|---|---|
| 1 | ~~diagnose~~ **done** — now re-run notebook 04's forecast pull | a few min | Recovers `rain_fcst_*` for all 7 years, the second-most-valuable input in the project |
| 2 | **Phase 1.5** — pull OSM road centrelines, buffer 5–10 m, re-sample terrain on roads only | half a day | Removes the building contamination and produces real road elevation |
| 3 | Add to the BMA data request: *what is `DTM_1M`?* | one email | Determines whether step 2 is a workaround or the permanent answer |
| 4 | Carry the ERA5-vs-gauge ratio (3.2× vs 13.6×) into the BMA meeting pack | none | Turns "we need radar" from an assertion into a measurement |
| 5 | Proceed to Phase 3 (notebook 05) using terrain **only from open districts**, flagged | — | Do not block the feature pipeline on step 2; mark the contaminated columns |

**Phase 3 is not blocked.** The flood, rain, water and flow features are
unaffected by any of the above. Terrain enters the feature table with a quality
flag, and the flag is honest about which districts it can be trusted in.
