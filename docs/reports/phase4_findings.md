# Phase 4 — The models

Written 9 August 2026, updated the same evening after all three notebooks were
run on the full grid: 4 folds × 3 tiers × 3 horizons, 72 models plus 24 quantile
models. Every number below is a mean across all four folds unless stated.

An earlier draft quoted fold 1 only. Fold 1 is the most optimistic fold, and the
figures here are lower.

---

## 1. What was built

| File | What it does |
|---|---|
| `src/bkkflood/models.py` | feature-set rules, negative downsampling, the three trainers, fold runner |
| `notebooks/07_train_lightgbm.ipynb` | general model — every row |
| `notebooks/08_train_onset.ipynb` | onset specialist — dry roads only |
| `notebooks/09_train_depth_quantiles.ipynb` | how deep, with an interval |

58 tests pass.

---

## 2. The result

15 cm, 1 hour ahead, mean across four folds.

| | PR-AUC | Precision | Recall | **Onset recall** | **Event POD** | Median lead |
|---|---|---|---|---|---|---|
| **onset specialist** | 0.103 | 0.163 | 0.229 | **0.229** | **0.599** | 15 min |
| general LightGBM | 0.566 | 0.631 | 0.558 | 0.190 | 0.487 | 15 min |
| rain_rule | 0.104 | 0.107 | 0.315 | **0.218** | — | — |
| persistence | 0.553 | 0.618 | 0.544 | 0.164 | — | — |
| climatology | 0.001 | 0.002 | 0.104 | 0.095 | — | — |

The specialist leads on both metrics that describe a warning system. But the
margin is the story, and it is uncomfortable.

### The onset specialist beats "alert when it rains" by 1.1 points

22.9% against 21.8%. A gradient-boosted model with 47 features, four folds of
training and a tuned threshold is **one percentage point** better at spotting
floods on dry roads than the rule *the rainfall in this district crossed a
number*.

That is the single most important sentence in this report. It should be said to
BMA in those words, because it sets the honest expectation for what the current
data can support — and it makes the case for the missing datasets in section 8
far better than any argument about model architecture.

### The general model is a thermometer

0.566 PR-AUC against persistence's 0.553 — a 2.4% improvement for 47 features
over "assume nothing changes". On onset rows it manages 0.190 against
persistence's 0.164.

### Every model has a median lead of 15 minutes

One modelling time step, at every tier, every horizon, every fold. Floods are
being caught just as the water arrives, not ahead of it. Detection is real;
dispatch is not possible on it. **Lead time, not PR-AUC, is the Phase 5
objective.**

---

## 2a. Four things the full grid showed that one fold could not

### Even the specialist mostly reads the depth sensor

Share of total gain for the onset model, most recent fold, 15 cm / 1 h:

| Feature family | Share of gain |
|---|---|
| the station's own depth history | **86.8%** |
| rainfall | 2.3% |
| calendar / tide | 2.1% |
| canal water and flow | 0.6% |
| **terrain** | **0.0%** |

Removing every already-flooded row was supposed to force the model toward
rainfall and terrain. It did not. `fl_hours_since_5cm` and its relatives still
dominate: the strongest available predictor of a road flooding is *how recently
that same road was last wet*.

**Terrain contributes exactly nothing.** This is not evidence that terrain is
irrelevant to urban flooding — it is evidence that a *district-average* elevation
is useless, because every station in a district gets the same number. The 1 m DTM
work in Phase 1 was done correctly and cannot pay off without station
coordinates. That is the strongest argument yet for BMA request #1.

### Performance appears to degrade toward the present — it does not

Onset specialist, 15 cm / 1 h, per fold:

| Test year | PR-AUC | Base rate | **Lift over base rate** | Onset recall | Event POD | Positives |
|---|---|---|---|---|---|---|
| 2022 | 0.129 | 0.00034 | **374×** | 0.283 | 0.630 | 1,193 |
| 2023 | 0.112 | 0.00015 | **753×** | 0.228 | 0.632 | 500 |
| 2024 | 0.078 | 0.00007 | **1,073×** | 0.199 | 0.600 | 251 |
| 2025 | 0.093 | 0.00017 | **563×** | 0.204 | 0.533 | 563 |

Raw PR-AUC falls by a third from 2022 to 2024, which looked alarming enough that
an earlier draft of this report called it a blocker for deployment. **That was
wrong, and the mistake was reading PR-AUC across years as if it were comparable.**

PR-AUC has a floor equal to the base rate. 2024 contains **251** onset positives
against 2022's **1,193** — Bangkok simply flooded far less. Dividing through,
the model's skill *relative to chance* is at its highest in 2024, the year that
looked worst: 1,073× against 374×.

Event POD, which does not depend on the base rate, tells the honest story:
0.630 → 0.632 → 0.600 → 0.533. A modest real decline, not a collapse. Onset
recall behaves the same way (0.283 → 0.204), and both track the rise in missing
sensor readings — 2.9% in 2022 to 10.7% in 2025 — rather than anything about the
model.

**The rule this establishes: never compare PR-AUC across years of differing
wetness.** Quote lift over base rate, or quote event POD. This is the same class
of error as reading raw recall without the onset split.

(Station churn was checked and is not a factor: only 5 of 107 stations first
appear in 2023, and they carry a similar positive rate to the rest.)

### Event POD rises with horizon, and that is an artefact

| Horizon | Onset recall | Event POD |
|---|---|---|
| 1 h | 0.229 | 0.599 |
| 3 h | 0.098 | 0.636 |
| 6 h | 0.090 | 0.709 |

Onset recall falls, as it must. Event POD *rises*, because the qualifying window
for an alert is `[water arrival − h, water arrival)` — a 6-hour model gets six
hours to fire, a 1-hour model gets one. **Event POD is not comparable across
horizons** and must never be quoted without its horizon attached.

### Deeper floods are easier to predict

Onset specialist at 1 hour: event POD 0.35 at 5 cm, 0.60 at 15 cm, **0.72 at
30 cm**. Severe floods are larger, wetter, more strongly forced events. Useful
operationally — the alerts that matter most are the most reliable — but the 30 cm
tier has only ~107 positive rows per test year, so treat it as encouraging rather
than established.

---

## 3. Two decisions that cost accuracy and were taken anyway

### 3.1 `era5_*` is excluded from every model

ERA5 is ECMWF reanalysis, published roughly **five days in arrears**. In the
feature table it is a legitimate record of past rain. As a model input it is
training/serving skew: populated offline, missing in production.

Measured on the onset specialist:

| | Onset PR-AUC |
|---|---|
| with `era5_rain_3h` | 0.160 |
| **without (deployed)** | **0.129** |

It was worth a fifth of the model and it is gone. **0.129 is the honest number;
0.160 describes a world where weather reanalysis arrives instantly.** Guarded by
`test_era5_is_never_a_model_feature`.

This is the kind of fault that normally surfaces in Phase 7, when the API returns
NaN, after the offline score has already been shown to somebody.

### 3.2 `rain_fcst_*` goes only to the onset specialist — now confirmed on the trained model

Phase 3 measured GFS with a crude proxy (the sum of past gauge rain and expected
forecast rain) and found a marginal +0.0008 onset PR-AUC gain. That test was
promised a re-run against the real model. Here it is, at 15 cm / 1 h, on the
three folds that have GFS in their training years:

| | PR-AUC | Onset recall | Precision | **Event POD** |
|---|---|---|---|---|
| with GFS | 0.097 | **0.239** | 0.148 | **0.651** |
| without GFS | 0.109 | 0.214 | 0.210 | 0.583 |
| **difference** | **−0.012** | **+0.025** | **−0.062** | **+0.068** |

Per fold (event POD, with → without): 2023 0.632 → 0.576, 2024 0.680 → 0.560,
2025 0.639 → 0.615.

Consistent in direction across all three folds. GFS accounts for roughly 5% of
the onset model's total split gain.

**The trained model extracts considerably more from GFS than the Phase 3 proxy
did** — a 12% relative improvement in event POD rather than a rounding error.
That is the outcome the Phase 3 caveat anticipated, and it is why the ablation
was worth repeating properly.

**But it is a trade, not a free win.** Roughly seven more floods caught per
hundred, before the water arrives, in exchange for six points of precision —
about one extra false alarm for each additional flood caught. PR-AUC gets slightly worse,
which is why PR-AUC is not the metric this project is steered by.

Under an F2 objective, and under the operational reality that a missed flood
strands traffic while a false alarm sends a patrol to a dry road, this is a good
trade. It is **BMA's call, not ours**, and it should be put to them in those
terms rather than presented as a technical decision already taken.

Fold 1 trains without it regardless — GFS begins 23 March 2021 and an imputed
forecast is an invented one.

---

## 4. Negative downsampling, and the correction it requires

Five training years is 17.6 M rows × 51 features, about 3.6 GB. Every positive is
kept; negatives are sampled (5% general, 25% onset — onset rows are already the
rare subset and thinning them discards the signal).

Sampling negatives at rate *r* multiplies the odds by 1/*r*.
`correct_for_downsampling` multiplies them back. Ranking is untouched, so PR-AUC
and thresholds are unaffected — but the **number** changes, and that number ends
up inside a CAP message. A model trained at 5% reports roughly twenty times the
true risk if this is skipped.

---

## 5. Depth quantiles fail their coverage check, at every horizon and every fold

The 5th/95th percentile interval was asked for 90% coverage.

| Horizon | Coverage, all rows | **Coverage, wet rows** |
|---|---|---|
| 1 h | 0.999 | **0.629** |
| 3 h | 0.997 | **0.433** |
| 6 h | 0.996 | **0.440** |

Configured tolerance: 0.85 – 0.93. Per fold, wet-row coverage runs 0.39 – 0.67.
Nothing comes close, and it is worst at the long horizons where a depth estimate
would be most valuable.

**The all-rows figure of 0.999 is meaningless** — 99% of rows are dry and the
interval `[0, 0]` covers them. Median interval width is 0.0 cm: the model has
learned to predict "no water" and is right almost always.

**These intervals must not be published as a p95.** An interval that claims 90%
and delivers 43% is worse than no interval, because it will be believed. In
order of preference for Phase 5:

1. train the depth model on **wet rows only**, so zeros do not dominate it
2. widen the quantiles until measured coverage meets the target
3. report a point estimate and state the coverage failure

## 6. A metric correction that changed the story

`event_pod` was rewritten during this phase, and the Phase 3 report was corrected
as a result.

The original defined an event as a run of positive **labels** and measured lead
from the start of that run. A label at *t* means "water arrives in (t, t+h]", so
a label run begins up to *h* hours before the flood — requiring an alert before
it is requiring a forecast of a forecast. It also credited alerts fired for a
*different, earlier* flood at the same station, which is how persistence reported
a 150-minute median lead when by construction it cannot fire before a road is wet.

Reported event POD for persistence went from **1% to 57%**. Events are now runs
of observed depth at or above the tier, with lead measured from the water's
arrival. Both faults have regression tests.

That is the fifth time in this project that a check, not the data, was the broken
thing. The pattern is consistent: every one of them reasoned from derived
quantities instead of recomputing from the source.

---

## 7. What would actually move the numbers

The models are not the bottleneck. A 1.1-point margin over a rainfall threshold,
with 87% of the gain coming from one station's own depth history and 0% from
terrain, is the signature of a **data** limit rather than a modelling one.

In order of expected effect:

| Missing | Why it matters here | What to ask for |
|---|---|---|
| **Station coordinates** (water + flow sensors) | terrain contributes 0.0% because every station in a district shares one elevation; canal features are citywide, so the model can never know *which* canal is backing up next to *this* road | one spreadsheet: code, lat, lon, for 300 water and 30 flow sensors |
| **Weather radar** | rainfall is 2.3% of gain, against one gauge per ~12 km² and convective cells 2–5 km across — the district average smooths away the peak that causes the flood | TMD radar feed |
| **Pump and gate status** | a flood a pump prevented is recorded as "no flood", so the model is trained against a partly counterfactual target | `pumps.bangkok.go.th` (ask first) |
| **Tide gauge** | `tide_*` is astronomy: correct phase, no height. A spring tide during a surge is indistinguishable from a calm one | one Chao Phraya gauge |

The first row is a spreadsheet and would let Phase 1's 1 m terrain work pay off.
It is the highest-value thing this project can ask BMA for.

---

## 8. Carried into Phase 5


1. **Lead time is the objective**, not PR-AUC. Fifteen minutes is not a warning,
   and it did not vary across any tier, horizon or fold.
2. **Fix or withdraw the depth intervals.** 62% coverage cannot ship.
3. **Re-run the GFS ablation** on the trained onset model. The Phase 3 result
   was marginal (61% of a +0.0008 gain).
4. **30 cm is not trainable** — around 43 positive rows a year. Report as a data
   limitation, never as a score.
5. **Calibration is unverified.** Brier scores are recorded; reliability curves
   are not yet plotted, and a probability inside a CAP message needs them.
6. **The decay toward the present is resolved — it was a base-rate artefact.**
   See section 2a. Remaining real effect: event POD drifts 0.63 → 0.53 as sensor
   outage rises from 2.9% to 10.7%. Phase 5 should quantify that link directly.
7. **Report the 1.1-point margin over `rain_rule` to BMA plainly.** It is the
   most useful number in this report and the strongest case for section 7.
