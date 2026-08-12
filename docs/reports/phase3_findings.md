# Phase 3 — Features and baselines: what was built and what was found

Written 7 August 2026, updated 9 August 2026 after both notebooks were run end
to end on the full seven-year archive.

Every number here comes from that run, not from a sample. Where a figure
contradicts an earlier document — including an earlier draft of this one — the
superseded claim is named so it can be traced. Section 3 in particular was
revised downwards: a two-year sample had overstated the value of the GFS
forecast by roughly a factor of two.

---

## 1. What now exists

| Artefact | What it is |
|---|---|
| `src/bkkflood/features.py` | 51 model inputs, built in DuckDB, streamed to Parquet |
| `src/bkkflood/labels.py` | forward-looking targets at 3 tiers × 3 horizons |
| `src/bkkflood/evaluate.py` | metrics, written out in numpy rather than imported |
| `src/bkkflood/baselines.py` | the four baselines |
| `data/features/features_YYYY.parquet` | 7 years, ~3.5 M rows × 79 columns, ~75 MB each |
| `notebooks/05_features.ipynb` | build, audit, leakage checks, the GFS decision |
| `notebooks/06_baselines.ipynb` | the bar, recorded before any model exists |
| `tests/` | 54 tests, under a second |

---

## 2. The baselines — the bar Phase 4 has to clear

**15 cm depth, 1 hour ahead, averaged over the four rolling-origin folds.**

| Baseline | PR-AUC | Precision | Recall | **Onset recall** | **Ongoing recall** |
|---|---|---|---|---|---|
| persistence | 0.553 | 0.618 | 0.544 | **0.164** | **1.000** |
| rain_rule | 0.104 | 0.107 | 0.315 | **0.218** | 0.443 |
| climatology | 0.001 | 0.002 | 0.104 | 0.095 | 0.116 |
| always_negative | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

Base rate: 0.0004 — about 1 positive row in 2,300.

### The two things this table says

**First, the headline recall of a monitor is meaningless.** Persistence — "the
road will be as it is now" — recovers **100%** of already-flooded rows and
**16%** of dry ones. Reported as one number that is 54%, which sounds like half
a working system and is in fact a sensor readout.

**Second, and more useful: `rain_rule` beats persistence on onset recall**
(0.218 against 0.164) while losing badly on every overall measure. The two
halves of the problem want different inputs — current depth answers *is this
road wet now*, rainfall answers *is it about to be*. A single model optimising a
single number will spend its capacity on the first question, because that is
where the rows are. This is the empirical case for the Phase 4 onset specialist.

### Event POD — and a correction

**An earlier version of this document reported an event POD of about 1% and
called it the sharpest number in the project. That figure was wrong, and it was
wrong because the metric was wrong.** The corrected numbers, 15 cm / 3 h, mean
per fold:

| Baseline | Events | Detected | **Event POD** | Median lead |
|---|---|---|---|---|
| persistence | 129 | 77.3 | **57.4%** | 15 min |
| rain_rule | 129 | 83.0 | **63.7%** | 22.5 min |

The original `event_pod` defined an event as a run of positive **labels** and
measured lead time from the start of that run. A label at time *t* means "water
arrives some time in (t, t+h]", so a label run begins up to *h* hours before the
flood. Requiring an alert before *that* is requiring a forecast of a forecast,
which is why almost nothing qualified. The same bug also credited an alert fired
for a **different, earlier** flood at the same station, which is how persistence
— a rule that cannot fire before a road is wet — reported a median lead of 150
minutes.

Events are now runs of **observed depth at or above the tier**, and lead is
measured from the moment the water actually arrived. Both faults are covered by
regression tests, including one asserting that an alert left over from a previous
flood earns no credit for the next.

### What the corrected numbers actually say

Persistence detects 57% of floods with a median 15 minutes of warning. That is
not the useless monitor the broken metric implied — because its tuned threshold
sits well below the tier (around 7–11 cm), so it fires while the water is *rising
toward* 15 cm. It is a genuine rising-water detector.

But 15 minutes is one modelling time step. It is real warning and it is not
enough to dispatch on, and that — not a fabricated 1% — is the honest statement
of the gap Phase 4 has to close.

### Decay with horizon (onset recall, 15 cm)

| Baseline | 1 h | 3 h | 6 h |
|---|---|---|---|
| persistence | 0.164 | 0.090 | 0.047 |
| rain_rule | 0.218 | 0.106 | 0.066 |
| climatology | 0.095 | 0.124 | 0.115 |

Everything decays except climatology, which is flat because it is a schedule and
a schedule does not care how far ahead you ask. If a Phase 4 model does *not*
decay with horizon, that is a leakage signal, not a triumph.

### Coverage and missingness, all seven years

From the notebook run — the sensor network grows, and so does the missing data.

| Year | Stations | Districts | Rows | GFS coverage |
|---|---|---|---|---|
| 2019 | 99 | 31 | 3,468,960 | 0.000 |
| 2020 | 99 | 31 | 3,478,464 | 0.000 |
| 2021 | 102 | 33 | 3,531,168 | 0.779 |
| 2022 | 102 | 33 | 3,574,080 | 1.000 |
| 2023 | 107 | 33 | 3,749,280 | 1.000 |
| 2024 | 107 | 33 | 3,759,552 | 1.000 |
| 2025 | 107 | 33 | 3,749,280 | 1.000 |

Rain, canal water, canal flow and terrain are at 1.000 for every year. **21 of
the 51 features have no missing values at all.** The flood-history block sits at
about 5% missing across the whole archive — higher than 2022's 2.9%, because the
rate climbs steadily to 2025.

`rain_fcst_*` is 30.5% null overall. That is not a defect; it is 2019, 2020 and
most of January–March 2021 having no forecast archive to draw on.

### The base rate is rarer than the single-year figure suggested

Label summary for 2024, the probe year:

| Tier | Horizon | Positives | Base rate | Onset share |
|---|---|---|---|---|
| 15 cm | 1 h | 377 | 1 in 9,154 | 66.6% |
| 15 cm | 3 h | 856 | 1 in 4,031 | 85.2% |
| 15 cm | 6 h | 1,566 | 1 in 2,203 | 91.9% |
| 30 cm | 1 h | 43 | 1 in 80,258 | 65.1% |

Two things to carry into Phase 4. **2024 is a much drier year than 2022** (377
positives against 2,687 at the same tier and horizon), which is why fold-level
results vary so widely and why nothing should be quoted from a single year.
And **the onset share rises to 92% at six hours** — the further ahead you ask,
the more of the job is genuine forecasting rather than remembering.

At 30 cm / 1 h there are 43 positive rows in a year. That tier is reportable but
not trainable on its own.

---

## 3. The GFS decision — measured, then made

The supervisor suggested GFS as a forecast input. It has a real cost: the
archive starts 23 March 2021, so fold 1 trains on two years with no forecast at
all. So it was measured before being adopted.

### Can GFS predict Bangkok rain, hour by hour?

**Essentially no.**

| | |
|---|---|
| Hours compared | 1,377,409 |
| Hours dry both ways | 77.7% |
| **Wet-hour correlation** | **0.014** |
| Wet-hour hit rate | 15.6% |

A 13 km global model over convective tropical rainfall, which is the expected
result. Reported on wet hours only — three quarters of hours are dry, so an
overall agreement figure would have measured agreement about nothing happening.
This project has already been misled by exactly that statistic once.

### Does it help predict floods anyway?

15 cm, 3 h, all five forecast years (2021–2025), 17,100,907 rows scored.

| Score | PR-AUC, **all rows** | PR-AUC, **onset rows** |
|---|---|---|
| gauge rain, past 3 h | **0.0512** | 0.0055 |
| GFS forecast alone | 0.0051 | 0.0037 |
| gauge + forecast | **0.0389** | **0.0068** |
| gauge + *seasonal control* | 0.0520 | 0.0060 |
| current depth (reference) | 0.3124 | 0.0375 |

**Read the two columns against each other.** Adding the forecast *improves*
onset discrimination by 24% (0.0055 → 0.0068) and *degrades* overall
discrimination by 24% (0.0512 → 0.0389).

That is not a contradiction, it is the whole finding in one line: the forecast
helps on the rows where forecasting is required, and adds noise on the rows
where the current depth reading already answers the question. Blended into a
single feature for a single model it is roughly a wash.

### The control

A forecast correlating at 0.014 should not be able to improve anything, so the
obvious suspicion is that it is not forecasting — it is telling the model that
August in Bangkok is wetter than January. To test that, every forecast value was
replaced by the *average* forecast for that district, month and hour: all of the
seasonality, none of the day-to-day skill.

| | |
|---|---|
| Total onset gain from the forecast | +0.00131 |
| ...that a calendar could explain | +0.00052 (39%) |
| **...genuine day-to-day forecast skill** | **+0.00079 (61%)** |

### Decision: keep `rain_fcst_*`, but narrowly and conditionally

The rule was "keep if most of the gain is not seasonality", and 61% clears it.
It clears it by less than it looks, and this should not be reported as a
comfortable result:

- The absolute gain is +0.0008 of onset PR-AUC against a baseline of 0.0055.
- On a two-year sample the same test gave +0.0024 with 72% real skill. On the
  full five years it is roughly **half that, with more of it seasonal**. The
  smaller sample flattered the feature, which is the usual direction.

Three conditions, and the third is new:

1. Fold 1 trains without those columns rather than imputing values that never
   existed.
2. Re-run the ablation in Phase 5 against the trained model. Treat it as a real
   decision point, not a formality — a gradient-boosted tree may extract more
   than a sum of two rainfall numbers, or may confirm this is noise.
3. **Give the forecast to the onset specialist, not to the general model.** The
   all-rows column above is the evidence: on the full row population it makes
   discrimination worse. Feeding it everywhere spends accuracy on the rows that
   did not need it.

---


## 4. Bugs found and fixed while building this

Recorded because three of the four were in a *check* rather than in the data,
which is now a pattern in this project rather than a coincidence.

### 4.1 The district join lost terrain for 16 of 33 districts

`_district_code_map()` maps 97 station prefixes onto 49 districts — rain, water,
flow and flood each use their own prefix for the same place. Inverting it to
name → prefix kept one arbitrary prefix per district and silently dropped the
rest. Terrain and GFS both came back 46.1% null.

Two unrelated feature blocks failing at *exactly* the same rate was the only
visible symptom. Now joined on district name; coverage is 33/33 and 100%.
Guarded by `test_district_join_uses_name_not_inverted_code`.

### 4.2 PR-AUC by trapezoid scored a perfect ranking at 0.50

A precision-recall curve doubles back on itself — precision drops vertically at
each false positive while recall stands still — so the trapezoid rule averages
across the drop. Replaced with the step sum (average precision), which is also
the conservative choice. Guarded by a regression test.

### 4.3 Threshold selection collapsed on a zero-inflated score

`best_threshold` built its candidate grid from evenly spaced quantiles. Flood
depth is zero in ~99% of rows, so every quantile from the 0th to the 99th was
0.0 and the grid jumped straight to the extreme tail. The useful range — a few
millimetres to a few centimetres — was never tested.

Measured on the real folds, persistence at 15 cm / 1 h chose:

| Fold | Threshold | Result |
|---|---|---|
| 2022 | 0.30 cm | plausible |
| 2023 | **0.00 cm** | alert on every row — 3,368,801 false alarms |
| 2024 | **0.00 cm** | 3,450,701 false alarms |
| 2025 | **44.10 cm** | four alerts all year, recall 0.4% |

Averaged, that produced a table reporting precision 0.31 beside 1.7 million
false positives — internally contradictory, and easy to read straight past. The
grid now also samples quantiles of the non-zero scores and of the scores on
positive rows. **Every number in section 2 is from after this fix.**

### 4.4 Two checks that were wrong rather than the data

- `check_features_against_raw` recomputed over `(t-3h, t]` while the feature
  uses the closed interval `[t-3h, t]`, and reported 28 mismatches in 250 rows.
  The feature was right.
- The window functions were rewritten from `ROWS` to `RANGE` on the theory that
  missing readings would stretch a 36-row window past three hours. They do not:
  across all 10,408,947 readings in 2022 the two forms agree on **every single
  row**, because the missing 2.9% are NULL *values* in rows that exist. The
  timestamp grid is unbroken. `RANGE` was kept anyway — it is correct by
  construction rather than correct by luck — at a cost of ~40 s per year.

### 4.5 A line continuation that survived into the notebook as `\\`

The notebook generator escaped a backslash twice, so `\` in the setup cell became
`\\` and the first cell of both notebooks failed with `SyntaxError: unexpected
character after line continuation character`. Rewritten to need no continuation.

Every code cell in both notebooks is now compiled *and executed* as part of the
build check — compiling alone would not have caught the four runtime errors that
followed, including `view()` returning a frame without the `tp`/`fp` columns a
later cell asked for.

### 4.6 Out-of-memory kills that looked like success

Twice, on a 3.9 GB machine: once assembling the feature table with
`pandas.merge`, once fitting climatology on four training years. Both were
killed by the kernel with no traceback, and with output piped an OOM kill is
indistinguishable from a clean exit that printed nothing. The joins and the
climatology fit now both happen in DuckDB.

---

## 5. What is still missing, and what it would buy

| Missing | Effect today | What we need |
|---|---|---|
| Station coordinates for water + flow sensors | canal features are **citywide** — the model knows the network is stressed, never *which canal* | one spreadsheet: station code, lat, lon |
| Weather radar | rain is a district average; one gauge per ~12 km² against cells 2–5 km across | TMD radar feed |
| Tide gauge | `tide_*` is astronomy — correct phase, no height | one Chao Phraya gauge |
| Pump/gate status | invisible; a flood that a pump prevented is unmarked | `pumps.bangkok.go.th` (ask first) |

The first row is the largest avoidable weakness in the feature set and it is a
spreadsheet away from being fixed.

---

## 6. Files to run

```bash
export PYTHONPATH="$PWD/src"
pytest tests/ -q                 # 54 tests, under a second
jupyter lab notebooks/
```

Then `05_features.ipynb` (~10 min) and `06_baselines.ipynb` (~6 min). Both have
been executed cell by cell against the real data; the leakage check in notebook
05 is the slowest single cell at about 90 seconds.
The feature Parquet is already built, so notebook 05 part 1 will simply
overwrite it with identical output.
