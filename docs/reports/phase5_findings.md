# Phase 5 — Honest evaluation

Written 9 August 2026. Notebooks 11–13, all executed against the full archive.
67 tests pass.

This phase produced two corrections to earlier claims and one finding that
should change what the project asks BMA for.

---

## 1. Correction: the model does not decay toward the present

Phase 4 reported that onset PR-AUC fell 0.129 → 0.093 from the 2022 fold to the
2025 fold "despite more training data", and called it a blocker for deployment.
That was wrong.

| Test year | PR-AUC | Base rate | **Lift over chance** | Onset positives | Event POD |
|---|---|---|---|---|---|
| 2022 | 0.129 | 0.00034 | **374×** | 1,193 | 0.630 |
| 2023 | 0.112 | 0.00015 | **753×** | 500 | 0.632 |
| 2024 | 0.078 | 0.00007 | **1,073×** | 251 | 0.600 |
| 2025 | 0.093 | 0.00017 | **563×** | 554 | 0.533 |

PR-AUC has a floor equal to the base rate. 2024 contains a fifth as many onset
positives as 2022 — Bangkok simply flooded less. Divide it out and the model's
skill relative to chance is **highest in the year that looked worst**.

**The rule this establishes: raw PR-AUC is comparable within a test year and
nowhere else.** Across years, quote lift over base rate or event POD. This is the
same class of error as quoting overall recall without the onset split.

The residual effect is real but modest: event POD drifts 0.63 → 0.53 while
missing sensor readings climb from 2.9% to 10.7%. Four points is far too few to
call that causal; it is a hypothesis, not a finding. Station churn was checked
and ruled out — only 5 of 107 stations first appear in 2023.

---

## 2. The main finding: this is a spatial resolution problem

Notebook 13's first attempt at a verdict asked "was rain recorded when we missed
the flood?" Rain *was* recorded on 82% of misses, which reads as "the signal was
there, the model failed". That conclusion is wrong, and the reason is worth
stating carefully, because it is the crux of the whole project.

**Every rainfall, terrain, canal and forecast feature is identical for every
station in a district.** So the question that matters is not whether rain was
recorded — it is whether the stations sharing that rain behave the same way.

Measured on 2025, district-hours with ≥5 mm of rain and ≥3 stations:

| | |
|---|---|
| Average share of a district's stations that flood | **2%** |
| When at least one floods, share of its neighbours that do | **35%** |

When a district floods, roughly one station in three is affected. The other two
experience the same recorded rain, the same district-average elevation, the same
citywide canal state — and stay dry.

**No model can separate rows whose inputs are identical.** The information that
would distinguish them — local elevation, the nearest canal, where the rain cell
actually sat — exists in the world and not in our data.

### What this implies

This reframes every earlier result:

- The onset specialist beats a rainfall threshold by **1.1 points** because
  rainfall at district resolution is close to all the discriminating signal
  there is.
- **87% of the model's gain** comes from each station's own depth history — the
  only input that differs between neighbouring stations.
- **Terrain contributes 0.0%** — not because urban terrain is irrelevant, but
  because a district-average elevation is the same number for every station in
  it.
- **Phase 6's sequence challenger will not fix this.** A larger model over the
  same inputs cannot recover information that was never measured.

The ranked data asks in `phase4_findings.md` section 7 are not a wish list. They
are the only route to a materially better system, and **station coordinates —
one spreadsheet — is first.**

---

## 3. Calibration

Test fold 2025, onset specialist, 15 cm / 1 h. Observed rate 1 in 6,042.

| Stage | Expected calibration error |
|---|---|
| raw LightGBM output (downsampled) | 0.000093 |
| **after the downsampling correction** | **0.000081** |
| after isotonic on top | 0.000084 |

The arithmetic odds correction works. **Isotonic calibration on top makes it
slightly worse** and is not recommended — there is not enough signal in the
positive class to fit a useful correction. At this base rate most reliability
bins contain fewer than 40 positives, and a bin holding ten positives cannot
support a claim about calibration however good its number looks.

One subtlety worth recording: isotonic regression is monotone *non-decreasing*,
not strictly increasing. It maps ranges of input onto a single output, creating
ties, so PR-AUC moved 0.0931 → 0.0921. Small, but the notebook previously
claimed ranking was untouched. It is very nearly untouched, which is not the
same thing.

**After correction the model is mildly UNDER-confident** — over-confidence ratios
run 0.3–0.5, meaning it predicts roughly half the observed rate. Under-confidence
is the safer direction, but it should be stated rather than presented as
calibrated.

---

## 4. Depth intervals cannot be published, and the fix is a two-stage model

Phase 4's 90% intervals covered 43–63% of wet rows. Three repairs were measured
on the 2025 fold. **None passes.**

| Variant | Coverage, wet rows | Coverage, all rows | Median width (wet) | Verdict |
|---|---|---|---|---|
| as-is (Phase 4) | 0.623 | 0.999 | 7.1 cm | too narrow — understates depth |
| wet rows only | **0.964** | **0.002** | 23.3 cm | too wide, and broken on dry rows |
| widened to 1/99 | 0.787 | 1.000 | 18.4 cm | still too narrow |

### The two failures are opposite, and that is the answer

"Wet rows only" covers wet rows well (96%) and dry rows essentially never
(0.2%) — trained on floods alone, it predicts a floor above zero everywhere.
"As-is" is the mirror image: fine on dry rows, far too narrow on wet ones.

Neither is one model's job. The fix is **two stages**: `P(flood)` from the onset
classifier, and depth-given-flood from the wet-rows-only quantile model, applied
only where the classifier fires. That is a Phase 6 build, not a parameter change.

**Until it exists and passes this same check:**

- do not publish a predicted depth or interval
- **drive CAP severity from the tier crossed** (5 / 15 / 30 cm), which is a
  classification the models already support

When the interval is wrong it is wrong by an average of **7 cm** — the difference
between a puddle and a stalled motorcycle.

---

## 5. What warning time actually looks like

Phase 4 reported a median lead of exactly 15 minutes everywhere, which is also
the modelling cadence — precisely what a broken measurement would look like. The
distribution settles it.

| | |
|---|---|
| Events detected (2025, 15 cm / 1 h) | 53% |
| Median lead | 15 min |
| Mean lead | 21 min |
| Maximum lead | 60 min |
| **Detections with only one time step of warning** | **75%** |

It is a real ceiling, not an artefact. Three quarters of detections come at the
last possible moment. **This is a detection system, not yet a warning system**,
and that is how it must be described to BMA.

---

## 6. The operational number nobody has asked for yet

Precision is the wrong unit for a staffing conversation. On the 2025 test year:

| | |
|---|---|
| Alert rows raised | ~large |
| Distinct alert episodes (merging alerts <60 min apart at a station) | see report |
| **Episodes per detected flood** | **6.6** |
| Events detected | 53% |

**For every flood the system successfully warns about, it generates about six
and a half separate call-outs.** That is the number BMA will care about most, and
it is not in any earlier document.

---

## 7. Carried into Phase 6

1. **Build the two-stage depth model.** Classifier × wet-rows quantile model,
   re-checked against `quantile_coverage`.
2. **Temper expectations for the sequence challenger.** Section 2 says the
   ceiling is resolution, not capacity. Run it, but promote it only on onset
   recall and event POD, and expect little.
3. **Reduce alert episodes per event.** 6.6 is probably the biggest usability
   problem in the system. Alert de-duplication and hysteresis are cheap and
   untried.
4. **Do not use isotonic calibration.** The downsampling correction alone is
   better at this base rate.
5. **Lead the BMA conversation with section 2.** The 35% figure makes the case
   for station coordinates better than any argument about model architecture.
