# Phase 0 — Verification against the Master Spec

*Generated 8 August 2026 from notebooks 00–02, run end to end on the full archive.*

Phase 0's acceptance criterion in the spec is: **"Every number in Part B
reproduces from the notebooks."** This file records that comparison honestly —
including the five places where the notebooks disagreed with the spec and the
spec turned out to be wrong.

Nothing below is retyped by hand. Every "notebook" column comes from a CSV in
`docs/reports/phase0/`.

---

## 1. Confirmed — the spec was right

| Claim (spec §) | Spec | Notebooks | |
|---|---|---|---|
| Total rows across four datasets (§B.1) | 392.9 M | **392,909,188** | ✅ |
| Flood rows (§B.1) | 75,932,352 | **75,932,352** | ✅ |
| Rain rows (§B.1) | 96,153,700 | **96,153,700** | ✅ |
| Water rows (§B.1) | 198,730,656 | **198,730,656** | ✅ |
| Flow rows (§B.1) | 22,092,480 | **22,092,480** | ✅ |
| Duplicate (station, timestamp) pairs (§B.3) | 0 | **0** | ✅ |
| Flood readings null (§B.4) | 4.98% | **4.9811%** | ✅ |
| Readings ≥ 5 cm (§B.4) | 50,929 — 1 in 1,491 | **50,929 — 1 in 1,491** | ✅ |
| Readings ≥ 15 cm (§B.4) | 15,024 — 1 in 5,054 | **15,024 — 1 in 5,054** | ✅ |
| Readings ≥ 30 cm (§B.4) | 3,262 — 1 in 23,278 | **3,262 — 1 in 23,278** | ✅ |
| Deepest reading ever (§B.4) | 148.8 cm | **148.8 cm** | ✅ |
| Station counts by year, all four datasets (§B.3) | as tabled | **identical** | ✅ |
| Null-rate trend 2019→2025 (§B.3) | flood 0.00 → 10.70% | **0.00 → 10.70%** | ✅ |
| Prefix coverage of 33 flood districts (§B.7) | rain 33/33, water 13/33, flow 3/33 | **33/33, 13/33, 3/33** | ✅ |
| Registry: sensors with any coordinate (§B.8) | 401 of 568 | **401 of 568** | ✅ |
| 1 m DTM covers the whole Bangkok boundary (§B.9) | yes | **yes** | ✅ |
| `FW.SSM.01` is flat zero for seven years (§B.6) | yes | **yes** | ✅ |
| `wl_out01` / `wl_out02` null share (§B.6) | 81.8% / 99.6% | **81.8% / 99.6%** | ✅ |

---

## 2. Corrections — the spec was wrong

### 2.1 The event count: **999 → 837** (spec §B.4)

The spec's headline number — *"999 flood events at the 15 cm tier"* — is the
count of excursions surviving the **persistence** rule only. It was computed
before the merge-gap and minimum-duration rules were applied. The full definition
gives **837**.

The chain, all from `notebooks/02`:

| Stage | 5 cm | 15 cm | 30 cm |
|---|---|---|---|
| Raw excursions (any run above the tier) | 5,281 | 1,469 | 342 |
| After persistence (≥ 2 consecutive readings) | 3,749 | **999** ← the spec's figure | 179 |
| After 60-minute merge + 10-minute minimum | **3,135** | **837** | **132** |

**Does it change the argument?** No. The spec uses this number to argue that
there is nowhere near enough data to train a Transformer or a Temporal Fusion
Transformer, and that gradient-boosted trees with onset specialists are the right
choice. 837 makes that argument slightly *stronger*, not weaker. But the number
itself is now correct and reproducible.

### 2.2 Events and durations per year (spec §B.4)

The spec's per-year table was also the pre-merge count. Corrected:

| Year | 5 cm | 15 cm | 30 cm | Stations hit (15 cm) |
|---|---|---|---|---|
| 2019 | 367 | 97 | 27 | 45 |
| 2020 | 432 | 110 | 17 | 38 |
| 2021 | 593 | 138 | 15 | 50 |
| 2022 | **774** | **235** | 30 | 56 |
| 2023 | 384 | 99 | 17 | 56 |
| 2024 | **253** | **46** | **7** | 25 |
| 2025 | 332 | 112 | 19 | 49 |
| **Total** | **3,135** | **837** | **132** | 83 distinct |

2022 remains the worst year and 2024 the quietest — a 5× difference at the 15 cm
tier, not 6× as the spec implies.

**Duration.** The spec says "median event duration 15–25 minutes". That was the
median *excursion*, before merging. Under the full definition the median **event**
at 15 cm lasts **45 minutes** (p25 = 25, p75 = 95, p90 = 185). The characterisation
still holds — 61% of events are over within an hour and 90% within three — but the
number was wrong.

### 2.3 The rainfall ceiling: hypothesis not supported (spec §B.5)

The spec says the exact 30.0 mm maximum for `rf5min` "suggests instrument
saturation or a capped field" across the gauge network, and flags it as a
question for BMA.

Measured: **one gauge of 131 reaches 30.0 mm.** The remaining 130 top out between
12 and about 25 mm, in a smooth distribution of station maxima. There is no shared
ceiling — there is one gauge that recorded a genuinely extreme five minutes.

The hypothesis was reasonable and it is wrong. It is worth still *mentioning* to
BMA, but it should not appear on the data-request list as a defect.

> **A process note worth keeping.** While investigating this, the range check in
> `config.yaml` was set to null any `rf5min` above 25 mm — which silently deleted
> the exact readings needed to answer the question, and made the notebook report
> "0 of 131 gauges reach 30.0 mm". A validity check placed close to real values
> stops being a check and becomes a hidden edit. The ceiling is now 60 mm.

### 2.4 "Every station-year has exactly 105,120 rows" (spec §B.3)

True for **3,730 of 3,736** station-years, not all of them. Six exceptions, in two
groups:

| Station | Year | Rows | Why |
|---|---|---|---|
| FL.MBR.01 | 2021 | 40,320 (38%) | Sensor **installed** 14 Aug 2021 |
| FL.DST.08 | 2021 | 41,184 (39%) | Sensor **installed** 11 Aug 2021 |
| RF.PYT.02 | 2022–2025 | 104,833 each (99.73%) | Export truncates 31 December at 00:00 — 287 rows short, every year |

129,884 rows in total, 0.033% of the archive. The conclusion is unchanged — the
time grid is essentially complete and duplicate-free — but "exactly" was too
strong. The two 2021 sensors are not a defect at all: they did not exist yet, and
any per-station statistic for 2021 must be computed over the station's lifetime
rather than the calendar year, or they will look like catastrophic outages.

### 2.5 Archive size: 51.1 GiB, not 54.8 GB (spec §B.1)

Both are correct; they are different units. 54.9 GB decimal (10⁹ bytes) = 51.1 GiB
binary (2³⁰ bytes), which is what `du`, Finder and Explorer report. Notebook 00
now prints both. The spec should say **51.1 GiB / 54.9 GB** to avoid an argument
in a meeting.

---

## 3. New findings — not in the spec at all

### 3.1 Flooding is more concentrated than assumed

24 of 107 flood sensors have **never recorded an event** at the 15 cm tier, and 69
of 107 have never recorded one at 30 cm. The ten worst sites produce 298 of 837
events — **36% of all flooding from 9% of the sensors**.

| Site | Events at 15 cm | Total minutes flooded | Deepest |
|---|---|---|---|
| FL.SMI.01 | 48 | 2,610 | 51.5 cm |
| FL.PWT.02 | 38 | 6,335 | 43.2 cm |
| FL.DDG.02 | 32 | 2,600 | 34.7 cm |
| FL.SLG.03 | 31 | 3,390 | 40.3 cm |
| FL.DDG.01 | 29 | 1,150 | 29.9 cm |

Directly useful for the dashboard's hotspot panel. Also a warning for the model:
"this place floods often" is a strong predictor, but it is climatology, and it
says nothing about a sensor installed last year.

### 3.2 The onset/ongoing split, measured for the first time

Of the 15,024 readings at or above 15 cm, **51% are ongoing** (the station was
already flooded an hour earlier) and **49% are onset** (it was dry). Only the
onset half requires forecasting; the ongoing half is answered by a one-line
persistence rule.

Base rate of an onset row: **1 in 9,868**.

This is the measurement behind the spec's insistence that recall be reported
twice, and behind the rule that onset models may raise a Watch but never a
Warning.

### 3.3 The event definition, stress-tested

Event count at 15 cm under different rules (rows = consecutive readings required,
columns = merge gap in minutes):

| | 0 | 15 | 30 | **60** | 120 | 180 |
|---|---|---|---|---|---|---|
| 1 | 999 | 898 | 867 | 859 | 853 | 848 |
| **2** | 999 | 885 | 851 | **837** | 827 | 823 |
| 3 | 841 | 782 | 765 | 754 | 745 | 742 |
| 4 | 740 | 706 | 694 | 684 | 674 | 672 |
| 6 | 597 | 579 | 573 | 569 | 563 | 560 |

The configured choice (2 readings, 60 minutes) sits at the elbow of both curves:
the 1→2 step removes noise, 2→3 starts removing real short floods; 0→60 minutes
stops one flooded afternoon being counted a dozen times, and past 60 the curve
flattens. Previously this choice was asserted. Now it is measured, and a reviewer
who prefers different values can see exactly what they would cost.

### 3.4 Near-zero readings collapse after 2021

Readings with `0 < depth < 5 cm` fall off a cliff: 141,869 in 2019 and 151,421 in
2021, but only 23,921 in 2022 and about 10,000 a year after that — while readings
**above** 5 cm do not show the same collapse. That looks like a change in sensor
reporting or rounding rather than a change in the weather. It does not affect the
tiers we model at, but anyone using `depth > 0` for anything should know.

---

## 4. Phase 0 acceptance checklist

| Criterion | Status |
|---|---|
| `config/config.yaml` is the single source of truth | ✅ no threshold, year or exclusion is duplicated in code |
| All 28 raw CSVs ingested to Parquet | ✅ 51.1 GiB → 1.12 GiB, 46× smaller |
| Row counts verified against the raw files | ✅ 28/28 exact |
| Sort order verified rather than assumed | ✅ 28/28 |
| Every Parquet has a provenance record | ✅ `data/interim/_manifest/*.json` |
| Quality scorecard, per station per year | ✅ 3,736 station-years |
| Flood event definition derived and stress-tested | ✅ §3.3 above |
| Class balance measured, not quoted | ✅ `class_balance.csv` |
| Every Part B number reproduces or is corrected | ✅ this document |
| Notebooks re-runnable end to end | ✅ 00 ≈ 60 s, 01 ≈ 10 s cached, 02 ≈ 35 s cached |

**Phase 0 is complete.** Next: Phase 1 — terrain features from the 1 m DTM
(`notebooks/03_terrain_from_dtm.ipynb`).

---

## 5. Where each number came from

| Output | Produced by |
|---|---|
| `inventory_*.csv` | `notebooks/00_data_inventory.ipynb` |
| `ingest_report.csv`, `ingest_range_flags.csv` | `notebooks/01_ingest_to_parquet.ipynb` |
| `quality_*.csv`, `class_balance.csv`, `flood_*.csv`, `event_definition_sensitivity.csv` | `notebooks/02_quality_and_events.ipynb` |
| `data/interim/_manifest/*.json` | `bkkflood.rawio.ingest_year_to_parquet` |
