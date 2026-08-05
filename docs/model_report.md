# Model Report — Bangkok Flood Forecast

*Answers evaluator points 1–8. Version 2.0. The version 1 report is preserved at
`archive/legacy_model_report_v1.md`.*

> **How to read this document.** Numbers marked **[v1]** come from the previous
> round of this project and are carried forward because they are informative and
> were honestly obtained. Numbers marked **[v2]** come from the rebuilt pipeline.
> The **[v2]** numbers in §5 and §7 come from a full run of notebooks 03–07 on
> this machine, with the supporting tables in `docs/reports/`.
>
> Nothing here is quoted without saying where it came from.
>
> **Status:** §5 carries an unresolved threshold-selection defect that holds
> precision far below what the trained models can reach. Read the boxed warning
> in §5 before quoting any precision, F1 or F2 figure from this run.

---

## 1. The problem

Predict road flooding at BMA sensor sites 1, 3 and 6 hours ahead, from rainfall,
canal water level, canal flow and recent flood depth.

Three things make it hard, and they compound:

1. **Extreme class imbalance.** At the 15 cm tier, roughly 1 positive row in
   4,000. A model that always says "no flood" scores 99.97% accuracy — which is
   why accuracy appears nowhere in this report.
2. **A trivial shortcut exists.** Current depth answers most of the question most
   of the time, so a model optimising a loss function will find it and stop
   learning anything else. Section 4 is about what that did to us.
3. **The rainfall input is spatially degraded.** District averages of a
   phenomenon that operates at 2–5 km. Section 7.

---

## 2. Definition of a flood event *(evaluator point 5)*

> A **flood event** is a period during which measured depth remains at or above a
> threshold for at least **two consecutive 5-minute readings**. Separate
> excursions less than **60 minutes** apart are merged into one event; events
> shorter than **10 minutes** are discarded as spikes.
>
> Tiers: **5 cm** nuisance (water on the road) · **15 cm** advisory (traffic
> disrupted — **all headline metrics are reported here**) · **30 cm** severe
> (impassable).

**Why not `depth > 0`.** In 2021, station FL.LSI.03 logged 21,754 non-zero
readings averaging 0.3 cm. That is instrument noise. Across the full archive 89%
of readings are exactly zero and only a fraction of a percent exceed 15 cm. A
threshold has to sit above the noise floor.

**Why two consecutive readings.** A single 5-minute spike is a splash, a passing
vehicle, or a corrupted packet. Requiring two removes most of it. Requiring three
or more starts discarding genuine short flash floods, which are common here — the
median event lasts well under an hour. Two is the elbow; `notebooks/02` measures
that rather than asserting it.

**Why merge at 60 minutes.** Depth flickers around a threshold. Without merging,
one afternoon of flooding becomes a dozen "events" and the event count means
nothing. The count falls steeply up to about an hour and then flattens; beyond
that we would start merging genuinely separate storms.

**The onset distinction.** A row where the station is already at or above the
threshold is **ongoing**; a row where it is below is **onset**. Only onset rows
require forecasting. Section 4.

---

## 3. Evaluation protocol *(evaluator point 7)*

**Rolling-origin cross-validation. Chronological. Never shuffled.**

```
fold 1   train 2019-2020            val 2021   test 2022
fold 2   train 2019-2021            val 2022   test 2023
fold 3   train 2019-2022            val 2023   test 2024
fold 4   train 2019-2023            val 2024   test 2025
```

- **A 24-hour embargo** at each year boundary. A label at 23:00 on 31 December
  looks six hours into the next year; without the embargo a sliver of validation
  leaks into training. Small, free to remove, impossible to argue with later.
- **Thresholds are chosen on the validation year and frozen** before the test
  year is touched.
- **Results are reported as a mean with the spread across folds.** Bangkok's
  flood years differ enormously, and "recall 0.31" hides the fact that it ranged
  from 0.18 to 0.44.

**Why not a random split.** Neighbouring 15-minute rows are near-identical.
Random splitting puts copies of the test rows into training and the model
memorises the answer — scores can look 20–30 points better than reality.

**On the final holdout.** The 2025 holdout was opened by version 1. Once a
holdout has informed any decision it stops being one. The rolling-origin folds
are therefore the headline evidence, and any 2025 figure is labelled as reused.
When 2026 data arrives, `config.yaml` switches the sealed holdout to it.

---

## 4. The central finding: onset versus ongoing

**This is the most important section in the report.**

Version 1 reported 55% recall at 15 cm, 1 hour ahead. Decomposed on the same
data: **[v1]**

| Population | Positive rows | Recall |
|---|---|---|
| Already flooded | 430 | ~100% |
| Genuinely dry — true onset | 413 | **9%** |

A one-line persistence rule — "if it is flooded now, say it will be flooded in an
hour" — achieves the first row perfectly. So the headline was carried almost
entirely by the half that needs no model at all. On the half that requires
forecasting, the system caught roughly one flood in eleven.

**Diagnosis.** `fl_depth_now` accounted for about **72% of total model gain**.
Given a feature that answers most of the question, gradient boosting will use it.
That is the algorithm working correctly, and the result was a monitoring system
wearing a forecasting label.

**Fix.** Train a separate model on **onset rows only** — rows where the station
is currently below the threshold. With the shortcut removed, the model has no
option but to learn precursors.

**Result** (sealed test-2025 at the time): **[v1]**

| Horizon | Onset recall, general model | Onset recall, onset model | Precision | Base rate | Lift |
|---|---|---|---|---|---|
| 1 h | 9% | **63.4%** | ~1.8% | 0.01% | ~38x |
| 3 h | — | 11.8% | ~0.65% | 0.01% | ~25x |
| 6 h | — | 4.7% | — | — | ~6x — **not deployed** |

**What the onset model learned instead of the shortcut:**

| Feature | Share of gain |
|---|---|
| `rain_rf1hr` | 56% |
| `rain_rf3hr` | 20% |
| `water_rising` | 5% |

Roughly **76% of the onset signal is rainfall**. That single table is the
strongest argument in this project for obtaining radar rainfall, and it is
evidence rather than intuition.

**Why onset output can only raise a Watch.** Precision around 1% means most
notices do not lead to flooding. That is fine for "check this" and unacceptable
for "close the road". The alert ladder was designed around the number we
measured, not the number we wanted.

---

## 5. Headline metrics *(evaluator points 1, 2, 3, 4, 6)*

Reported for every tier × horizon:

| Metric | Why it is here |
|---|---|
| **Precision** | Of the alarms raised, how many were real |
| **Recall** | Of the real floods, how many we caught |
| **F1** | Balanced summary |
| **F2** | Recall weighted 2× over precision — the right balance when a missed flood costs more than a wasted patrol |
| **False-negative rate** | **Reported as a miss rate**: "we miss 45% of floods" is the same fact as "recall 0.55" and lands very differently |
| **PR-AUC** | Threshold-free ranking quality; the right curve under extreme imbalance |
| **Alarms per hit** | The number operators actually complain about |
| **Event POD / lead time** | What a duty officer experiences |

### Version 2 results **[v2]**

Rolling origin, four chronological folds (2022–2025 as successive test years),
thresholds selected on the validation year and frozen before testing. Source:
`docs/reports/fold_summary.csv`. Mean across folds, with the range where the
spread matters.

**15 cm — the advisory tier**

| Horizon | Precision | Recall | Recall range | F1 | F2 | Miss rate (FNR) | PR-AUC |
|---|---|---|---|---|---|---|---|
| 1 h | 0.054 | 0.707 | 0.64 – 0.78 | 0.099 | 0.201 | 0.293 | 0.497 |
| 3 h | 0.063 | 0.385 | 0.30 – 0.46 | 0.107 | 0.187 | 0.615 | 0.264 |
| 6 h | 0.062 | 0.235 | 0.14 – 0.29 | 0.097 | 0.148 | 0.765 | 0.160 |

**5 cm and 30 cm**

| Tier | Horizon | Precision | Recall | F1 | F2 | Miss rate |
|---|---|---|---|---|---|---|
| 5 cm | 1 h | 0.154 | 0.612 | 0.244 | 0.379 | 0.388 |
| 5 cm | 3 h | 0.163 | 0.312 | 0.211 | 0.260 | 0.688 |
| 5 cm | 6 h | 0.161 | 0.189 | 0.169 | 0.179 | 0.811 |
| 30 cm | 1 h | 0.522 | 0.557 | 0.427 | 0.401 | 0.443 |
| 30 cm | 3 h | 0.262 | 0.347 | 0.206 | 0.216 | 0.653 |
| 30 cm | 6 h | 0.009 | 0.292 | 0.018 | 0.041 | 0.708 |

The configured 50% ceiling on the miss rate is breached in six of the nine
combinations — every 3 h and 6 h row. That is reported rather than fixed by
moving the threshold, which would only trade misses for false alarms.

**Event level, 2025, 1 h model.** Of 112 flood events the system warned about
111 (**POD 0.99**) with a **median 15 minutes** of lead time (mean 24.1). Event
POD far exceeds row recall because a long flood only has to be caught once.
False alarm ratio at the event level is 0.96.

> ### ⚠ These numbers understate the model, and are not yet fit to publish
>
> Precision collapsed to ~0.05 at the 15 cm tier because the selected
> thresholds are near zero — effectively "alarm on everything". `constraints_met`
> is `False` on 33 of the 36 fold rows.
>
> The cause is the candidate set in `threshold_sweep` (`src/bkkflood/metrics.py`),
> not the model. Candidates are evenly spaced **rank** quantiles, so the top two
> are the 99.5th percentile and the maximum, with nothing in between. At a base
> rate of 0.009% (294 positives in 3.45M validation rows) the optimum sits near
> the 99.99th percentile, which the grid cannot see. `pick_threshold` chooses
> correctly from a candidate set that omits every good option.
>
> Measured on fold 4 validation, `ge15_1h`, same booster, no retraining:
>
> | Threshold | Precision | Recall | F2 |
> |---|---|---|---|
> | 7.06e-05 *(selected)* | 0.048 | 0.568 | 0.180 |
> | 99.99th percentile | 0.387 | 0.456 | **0.440** |
>
> Changing the grid changes every operating point, so it is a modelling decision
> and has been left alone pending a call. Until it is resolved, the precision,
> F1 and F2 columns above should be read as a floor, not as the model's ability.

**Did it beat persistence?** On F2, **no — only 1 of 9** tier–horizon
combinations (5 cm at 6 h). Persistence scores F2 0.534 / 0.292 / 0.175 at the
15 cm tier against the model's 0.201 / 0.187 / 0.148. This is a direct
consequence of the threshold defect above: persistence holds precision ~0.83
while the model's collapses to ~0.05. Recall is higher for the model at every
horizon (0.707 vs 0.492 at 1 h).

**Two boosters collapsed.** `clf_ge30_1h` and `onset_ge15_1h` both trained to
`best_iteration = 1` — the class-imbalance collapse mode. They run without error
and are worthless. The 30 cm classifier was already known not to work and the
alert ladder routes severe through the P95 regressor instead, but
`onset_ge15_1h` is the model §4 is built on, so the 1 h onset figure below
should not be relied on.

**Depth bands are far too wide.** P05–P95 covers 99.9 / 99.7 / 99.6% of outcomes
against a 90% target, consistent with the `reg_q95` models stopping at 23–28
trees. An operator would find the band uninformative.

**Version 1 sealed-test results, carried forward for context** (15 cm tier): **[v1]**

| Horizon | Precision | Recall | F2 | Persistence F2 |
|---|---|---|---|---|
| 1 h | 0.64 | 0.55 | 0.565 | 0.553 |
| 3 h | 0.60 | 0.28 | 0.309 | 0.289 |
| 6 h | 0.68 | 0.15 | 0.183 | 0.170 |

In v1 the model beat persistence at every horizon. It no longer does, and the
threshold-resolution defect above is the reason — v1's precision of 0.64 is the
kind of operating point the current grid can no longer reach.

**The 6-hour horizon should be read carefully.** Station identity was the largest
single input there (~39% of gain) in v1, which means the model is substantially
saying "this place floods often". That is a form of skill, but it is climatology
rather than meteorology, and it should be described as such. In v2 the same
pattern holds for the onset models: `station_code` is 21% of gain at 3 h and 29%
at 6 h.

**What the 15 cm / 1 h model leans on now [v2]** — `fl_depth_now` no longer
dominates:

| Feature | Share of gain |
|---|---|
| `fl_std3h` | 68.9% |
| `rain_rf1hr_delta1h` | 10.6% |
| `station_code` | 4.5% |
| `fl_depth_now` | **1.6%** |
| `rain_fcst_3h` | 1.5% |
| `water_rising_share` | 1.1% |
| `rain_fcst_6h` | 1.0% |
| `cal_doy_sin` | 0.8% |
| `cal_doy_cos` | 0.8% |
| `water_rise1h_mean` | 0.8% |

This is the single biggest change from v1, where `fl_depth_now` carried ~72% of
gain. The v2 feature set added `fl_std3h` (trailing 3-hour variability of depth)
and the rain-change terms, and the model prefers them. Recent *variability* in
depth is a better precursor than the depth level itself — which is what a
forecasting model, rather than a monitoring one, ought to be using.

---

## 6. Alert policy

| Level | Raised by | Certainty in CAP |
|---|---|---|
| **Watch** | 5 cm classifier, or an onset model | Possible |
| **Advisory** | 15 cm classifier | Likely (Observed if already flooded) |
| **Warning** | P95 predicted depth ≥ 30 / 26 / 24 cm at 1 / 3 / 6 h, or current depth ≥ 30 cm | Likely (Observed if already flooded) |

**Why the severe tier uses the depth regressor, not a classifier.** The 30 cm
classifier never worked — too few positives (test PR-AUC ~0.04). The P95 quantile
regressor answers the same question far better (PR-AUC 0.52 / 0.22 / 0.12 at
1 / 3 / 6 h) because it learns from every row rather than only the rare ones. **[v1]**

**Why the Warning threshold falls with horizon.** The predicted band widens as
the forecast reaches further out. Holding the trigger at 30 cm would make
long-range warnings vanish entirely — not because the risk fell, but because the
uncertainty grew.

**Hybrid scoring.** Served scores are `max(model, persistence)`. Persistence is
perfect on already-flooded rows and useless elsewhere; the model is the opposite.
Taking the maximum keeps the easy wins, never lowers recall, and is trivial to
explain to an operator — which matters more here than elegance.

---

## 7. False positive and false negative analysis *(evaluator point 8)*

**The method that matters.** Sort the misses into two buckets:

1. **Rain was falling and we still missed it.** A model problem. The signal was
   present and we failed to use it. Worth working on.
2. **No rain recorded anywhere and the water arrived regardless.** Not a model
   problem. Either the rain fell between gauges — the district-average weakness
   again — or the water came from somewhere else: an upstream canal, a pump
   switching off, a blocked drain. No amount of tuning fixes this bucket. It
   needs radar, canal topology, or pump records.

**This split converts the evaluation into a data request**, which is why it is
the most useful hour available in the project.

### How the v2 misses actually split **[v2]**

Of the ten worst misses (`docs/reports/worst_false_negatives.csv`, 15 cm / 1 h,
test year 2025), **nine had essentially no rain recorded nearby** and one had
rain falling. The evidence points overwhelmingly at missing inputs rather than
at the model.

**Case study, reproduced in v2: FL.WTN.01, 8 February 2025.** **[v1]** **[v2]**
The v1 case study reappears unchanged as the three most confident misses of the
whole run — a rainless flash flood, `rain_rf1hr_mean` and `rain_rf3hr_mean` both
0.0, forecast rain 0.0, model score ~1e-12. Bucket 2. Either a highly localised
cell that fell between gauges, or water arriving through the canal network.
Unfixable with current inputs, and a concrete illustration of what radar
rainfall would address. That it survives a full rebuild, a new feature set and a
different split is good evidence it is a property of the data, not an artefact.

**A second pattern the v2 run exposes: 13 November 2025, 01:15–01:45.** Five
misses at FL.PYT.01/04/05/07 and FL.RTW.04 within half an hour of each other.
Gauge rainfall was 0.0, but `rain_fcst_3h` read **15.9 mm** — the weather model
knew rain was coming and the flood model still scored ~1e-11. This is Bucket 1,
and it is the more actionable of the two: the signal was present in an input we
already have.

**Concentration of errors [v2].** The top 10 stations account for **122 of 265
misses (46%)** across 100 stations. The worst are FL.SMI.01 (21 misses),
FL.BNA.04 (17) and FL.STN.03 (13). FL.SMI.01, FL.BNA.04 and FL.DDG.02 led the
same list in version 1 **[v1]** — the concentration is stable across versions,
which turns "the model misses 29% of flood rows" into a short list of specific
sites to investigate physically.

**The noisiest stations [v2].** FL.PWT.02 produced 1,441 false alarms against 20
real positives (precision 0.014) and FL.LSI.04 produced 1,017 against 5
(precision 0.005). A station with many false alarms and almost no real events is
usually a faulty sensor rather than a modelling problem, and should be checked
against the quality scorecard before anyone touches the model.

**Where the loudest false alarms come from — not the model.** Every one of the
ten worst false positives has `fl_depth_now` at or above 15 cm and a score of
exactly 1.0, which is the persistence half of `max(model, persistence)` firing.
They are rows where the road is genuinely flooded *now* but the water recedes
within the hour, so the forward-looking label is 0. That is a labelling
consequence of forecasting rather than a model error, and it is worth stating
plainly before anyone tries to tune it away.

---

## 8. Model selection

**The rule, fixed in `config.yaml` before any deep model was trained:**

> A deep model replaces LightGBM only if it beats it on validation PR-AUC for the
> primary tier at **both** 3 h and 6 h, by more than 0.01 absolute. Ties go to
> LightGBM.

**Version 1 outcome.** The GRU lost at 6 h by **0.0003** — a rounding error — and
was correctly not promoted. **[v1]**

**But the loser won somewhere specific**, and that is the more useful finding: on
the severe tier at 1 hour the GRU reached PR-AUC 0.38 where the LightGBM
classifier managed 0.0002. A targeted swap for that one tier is justified and is
on the roadmap.

Recording all three of *verdict*, *margin* and *where the loser won* is
deliberate. A loss by 0.0003 and a loss by 0.15 mean completely different things
about whether an approach is worth revisiting, and a single "which model won"
number destroys that distinction.

---

## 9. Calibration

Negative downsampling (5% of negatives kept) is necessary — uncapped class
weights of ~4,000 saturate the probabilities and early stopping fires after a
handful of trees. But it distorts the output scale: a raw score of 0.8 does not
mean an 80% chance of anything.

**Isotonic regression, fitted on validation data**, maps scores back to real
probabilities. It only assumes that higher scores mean higher risk, which suits a
distortion no simple formula describes.

**Why this is not optional.** The dashboard displays "68% risk" to an operator.
If rows predicted at 68% flood 4% of the time, that display is lying, and no
disclaimer fixes it. `notebooks/07` produces reliability diagrams; points below
the diagonal mean the system is overstating danger, points above mean it is
understating — and understating is the worse failure.

---

## 10. Known limitations

| Limitation | Effect | What would fix it |
|---|---|---|
| Rainfall is a district average | Localised cells smoothed away; caps onset detection | **Radar rainfall (TMD)** |
| Water and flow are citywide | Cannot localise drainage stress | **Station coordinates** |
| No canal topology | Cannot model propagation | Canal network from BMA GIS |
| No pump records | A control input is invisible to the model | Drainage operation logs |
| Terrain is 31 m SRTM | Cannot resolve road dips of 20–50 cm | LiDAR / 1 m DTM |
| Tide is reconstructed, not measured | Phase without amplitude | Chao Phraya tide gauge |
| Labels are sensor-only | Floods without a sensor are invisible to model *and* evaluation | Incident reports; more sensors |
| 2025 holdout is spent | No clean sealed test | 2026 data |
| No live BMA feed | Live mode is much weaker than the demo | Sensor API |

**One correction to the version 1 report.** `FW.PKG.01` was described there as a
faulty sensor because of its ±3,300 m³/s readings. It is not faulty: the station
is the Rama VIII Bridge gauge on the Chao Phraya **river**, and those are
plausible tidal river discharges. It is still excluded from canal features, but
as a **scale mismatch** — a river a thousand times larger than the canals it
would otherwise be averaged with — not as a fault. The distinction matters when
explaining the system to BMA, who know perfectly well that the gauge works.

---

## 11. Reproducing everything here

```bash
export PYTHONPATH="$PWD/src:$PWD"
jupyter lab notebooks/
```

Run `00` → `09` in order. Notebook `07` regenerates every table in this report
and writes them to `docs/reports/`.

Every threshold, horizon and split is defined in `config/config.yaml`. Nothing in
this project keeps a second copy of any of them.
