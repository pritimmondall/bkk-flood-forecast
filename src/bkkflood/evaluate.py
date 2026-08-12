"""
Scoring a flood forecast honestly.

--------------------------------------------------------------------------
WHY NOT scikit-learn
--------------------------------------------------------------------------
These are twenty lines of numpy and they are the numbers the whole project is
judged on. Written out here, the definitions can be read and argued with. The
alternative is a stack of imported one-liners whose averaging conventions
nobody checks — and `average_precision_score` and the area under a
precision-recall curve are not the same number, which matters a great deal when
positives are 1 row in 1,291.

--------------------------------------------------------------------------
THE THREE THINGS THAT MAKE A FLOOD SCORE MISLEADING
--------------------------------------------------------------------------
**1. Accuracy is meaningless here.** Predicting "no flood" forever scores
99.92%. Accuracy is not computed by this module at all.

**2. A single recall number describes a monitor, not a forecaster.** The
previous version of this project reported 55% recall. Split apart, that was
~100% on rows where the road was ALREADY flooded and 9% on genuine onsets. The
model had learned to repeat the current reading. `by_onset()` exists so that
cannot be reported again without the split.

**3. Row recall is not event recall.** A three-hour flood is 12 rows at
15-minute spacing. Catching 11 of them late looks like 92% recall and is a
failure; catching the first one is the entire job. `event_pod()` scores whole
events and always returns lead time beside the hit rate — an event caught with
five minutes' warning is not the same product as one caught with an hour's.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd

from .config import load_config


# ---------------------------------------------------------------------------
# Threshold metrics
# ---------------------------------------------------------------------------
def binary_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    """Confusion-matrix metrics at an already-chosen threshold.

    `f2` is the project's primary metric. It weights recall twice as heavily as
    precision, which is the honest encoding of the operational trade-off: a
    missed flood strands traffic and puts BMA in the news, a false alarm sends a
    patrol to a dry road.

    `fnr` — the false-negative rate — is reported explicitly because it is the
    number the evaluator asked for and the one an operations team actually
    feels. It is `1 - recall`, but writing it out stops anyone quoting 45%
    recall without noticing they have also said "we miss more than half".
    """
    y_true = np.asarray(y_true, dtype=bool)
    y_pred = np.asarray(y_pred, dtype=bool)

    tp = int(np.sum(y_true & y_pred))
    fp = int(np.sum(~y_true & y_pred))
    fn = int(np.sum(y_true & ~y_pred))
    tn = int(np.sum(~y_true & ~y_pred))

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0

    def fbeta(b: float) -> float:
        denom = (b * b * precision) + recall
        return (1 + b * b) * precision * recall / denom if denom else 0.0

    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": fbeta(1.0),
        "f2": fbeta(2.0),
        "fnr": 1.0 - recall,                     # the miss rate, stated plainly
        "far": fp / (tp + fp) if tp + fp else 0.0,   # false alarm ratio
        "positives": tp + fn,
        "alerts_raised": tp + fp,
    }


def average_precision(y_true: np.ndarray, scores: np.ndarray) -> float:
    """Area under the precision-recall curve, as a step sum rather than a trapezoid.

    PR-AUC rather than ROC-AUC, and the reason is not stylistic. With 1 positive
    in 1,291, a model can raise ten false alarms for every hit and still show a
    superb ROC curve, because the false-positive rate is diluted by an enormous
    negative class. PR-AUC has the positive class in both terms, so it cannot be
    flattered by imbalance.

    WHY A STEP SUM. The first version integrated the curve with `np.trapezoid`
    and scored a PERFECT ranking at 0.50. A precision-recall curve is not a
    function that can be trapezoid-integrated: precision jumps downward at every
    false positive while recall stands still, so the curve doubles back on
    itself and the trapezoid rule averages across the vertical drop. Summing
    `(R_n - R_{n-1}) * P_n` — the average precision — treats the curve as the
    staircase it actually is. It is also the conservative choice: trapezoid
    interpolation between PR points is known to read optimistically.

    The no-skill baseline is the base rate, not 0.5. A score of 0.10 sounds poor
    and is a 129-fold improvement over chance at a 1-in-1,291 base rate. Always
    quote the base rate beside it.
    """
    p, r, _ = pr_curve(y_true, scores)
    if r.size == 0:
        return 0.0
    return float(np.sum((r - np.r_[0.0, r[:-1]]) * p))


# The project's config and spec both say "PR-AUC"; this is that number.
pr_auc = average_precision


def pr_curve(y_true: np.ndarray, scores: np.ndarray):
    """Precision and recall at every distinct score, highest score first."""
    y_true = np.asarray(y_true, dtype=bool)
    scores = np.asarray(scores, dtype="float64")
    keep = ~np.isnan(scores)
    y_true, scores = y_true[keep], scores[keep]

    order = np.argsort(-scores)
    y_sorted = y_true[order]
    tp = np.cumsum(y_sorted)
    fp = np.cumsum(~y_sorted)
    total_pos = int(y_true.sum())

    precision = tp / np.maximum(tp + fp, 1)
    recall = tp / total_pos if total_pos else np.zeros_like(tp, dtype="float64")
    return precision, recall, scores[order]


def brier(y_true: np.ndarray, prob: np.ndarray) -> float:
    """Mean squared error of the probabilities — calibration and sharpness together.

    Low Brier scores are trivial on rare events (predict 0.001 everywhere), so
    this is only meaningful against the base-rate baseline, which `baselines.py`
    records first for exactly this reason.
    """
    y_true = np.asarray(y_true, dtype="float64")
    prob = np.asarray(prob, dtype="float64")
    keep = ~np.isnan(prob)
    return float(np.mean((prob[keep] - y_true[keep]) ** 2))


def best_threshold(y_true: np.ndarray, scores: np.ndarray,
                   metric: str = "f2", n_grid: int = 200) -> Dict[str, float]:
    """The threshold maximising `metric`, chosen on VALIDATION data only.

    Tuning a threshold on the test set is the quietest way to overstate a
    result: it is not leakage of features, it is leakage of the decision, and it
    typically buys several points of F2 that do not exist in production. The
    rolling-origin folds keep a separate validation year for this.

    WHY THE CANDIDATE GRID IS BUILT THE WAY IT IS
    ---------------------------------------------
    The obvious implementation — evenly spaced quantiles of the score — fails
    badly here, and it fails silently. Flood depth is zero in about 99% of rows,
    so every quantile from the 0th to the 99th is 0.0 and the grid leaps from
    0 cm straight to tens of centimetres. The useful range, a few millimetres to
    a few centimetres, is never sampled at all.

    Measured on the real folds: persistence at 15 cm / 1 h chose a threshold of
    0.0 in two of four folds (alert on every row: 3.4 million false alarms,
    recall 100%) and 44.1 cm in a third (four alerts all year, recall 0.4%).
    Only one fold landed anywhere sensible. Averaged across folds that produced
    a precision of 0.31 sitting next to 1.7 million false positives — a table
    that is internally contradictory and would have been read straight past.

    So the grid is the union of three sets: quantiles of all scores, quantiles
    of the NON-ZERO scores, and quantiles of the scores on POSITIVE rows. The
    last is the important one — it puts candidates exactly where the classes
    actually separate. All three come from validation data only.
    """
    scores = np.asarray(scores, dtype="float64")
    y_true = np.asarray(y_true, dtype=bool)
    finite = scores[~np.isnan(scores)]
    if finite.size == 0:
        return {"threshold": float("nan"), metric: 0.0}

    qs = np.linspace(0, 1, n_grid)
    parts = [np.quantile(finite, qs)]
    nonzero = finite[finite > finite.min()]
    if nonzero.size:
        parts.append(np.quantile(nonzero, qs))
    pos = scores[y_true & ~np.isnan(scores)]
    if pos.size:
        parts.append(np.quantile(pos, qs))
    grid = np.unique(np.concatenate(parts))

    best = {"threshold": float(grid[0]), metric: -1.0}
    for t in grid:
        m = binary_metrics(y_true, scores >= t)
        if m[metric] > best[metric]:
            best = {"threshold": float(t), **m}
    return best


# ---------------------------------------------------------------------------
# The two splits that stop a monitor being reported as a forecaster
# ---------------------------------------------------------------------------
def by_onset(y_true: np.ndarray, y_pred: np.ndarray,
             is_onset: np.ndarray) -> pd.DataFrame:
    """Metrics computed three ways: overall, onset only, ongoing only.

    ONSET means the station was BELOW the tier at time t — the road was passable
    and the model had to predict that it would not stay that way. ONGOING means
    it was already flooded, and "it will still be flooded in an hour" is a
    correct but nearly free prediction.

    Reporting only the overall row is how 9% onset recall got published as 55%.

    A fourth subset, `depth_unknown`, holds rows where the current reading is
    missing — 2.9% in 2022, rising to 10.7% by 2025. Those rows are neither
    onset nor ongoing and there is no defensible way to guess: calling them
    onsets flatters the hard number, calling them ongoing flatters the easy one.
    They are counted separately so the three real subsets still add up.
    """
    y_true = np.asarray(y_true, dtype=bool)
    y_pred = np.asarray(y_pred, dtype=bool)
    onset = pd.array(is_onset, dtype="boolean")
    known = ~onset.isna()
    onset_np = onset.fillna(False).to_numpy(dtype=bool)

    rows = []
    for name, mask in (("overall", np.ones(len(onset_np), dtype=bool)),
                       ("onset", known & onset_np),
                       ("ongoing", known & ~onset_np),
                       ("depth_unknown", ~known)):
        mask = np.asarray(mask, dtype=bool)
        m = binary_metrics(y_true[mask], y_pred[mask])
        rows.append({"subset": name, "rows": int(mask.sum()), **m})
    return pd.DataFrame(rows)


def event_pod(df: pd.DataFrame, depth_col: str, pred_col: str, tier_cm: int,
              horizon_h: int, station_col: str = "station_code",
              ts_col: str = "ts", merge_gap_min: Optional[int] = None
              ) -> Dict[str, float]:
    """Probability of detection per EVENT, with lead time measured from the water.

    An event is a run of timestamps where the OBSERVED DEPTH is at or above the
    tier — the water actually being on the road — merged across short gaps by the
    same rule as `events.py`, so one flood is one flood everywhere in this
    project. Lead time is measured from the first qualifying alert to the moment
    the water arrived.

    WHY THIS WAS REWRITTEN
    ----------------------
    The first version defined events from runs of positive LABELS and measured
    lead from the label run's start. Two things went wrong, and they pointed in
    opposite directions so they did not cancel.

    A label at time t means "the water arrives some time in (t, t+h]", so a label
    run begins up to h hours before the flood. Lead measured against it is lead
    against a bookkeeping artefact, and it is not comparable between the 1, 3 and
    6-hour models — the same forecast scores differently purely because the
    horizon changed.

    Worse, the alert window `[start - h, start]` would credit an alert that was
    fired for a *different, earlier* flood at the same station. That is how
    persistence — which by construction cannot fire before a road is wet —
    reported a median lead of 150 minutes.

    Measuring from the water is the only definition that means what a BMA
    operations room would take it to mean.
    """
    cfg = load_config()
    gap = merge_gap_min or cfg["flood_event"]["merge_gap_minutes"]

    d = df[[station_col, ts_col, depth_col, pred_col]].dropna(subset=[depth_col])
    d = d.sort_values([station_col, ts_col])

    detected, leads, n_events = 0, [], 0
    for _, g in d.groupby(station_col, sort=False):
        wet = g[g[depth_col].to_numpy() >= tier_cm]
        if wet.empty:
            continue
        t = wet[ts_col].to_numpy()
        breaks = np.r_[True, (np.diff(t) > np.timedelta64(gap, "m"))]
        starts = t[breaks]
        n_events += len(starts)

        alerts = g.loc[g[pred_col].astype(bool), ts_col].to_numpy()
        for i, s in enumerate(starts):
            # An alert only counts if it precedes the water and belongs to THIS
            # event: no earlier than the horizon, and after the previous event
            # ended, so a still-running alert from the last flood cannot count.
            floor = s - np.timedelta64(horizon_h, "h")
            if i > 0:
                prev_end = t[t < s].max()
                floor = max(floor, prev_end + np.timedelta64(gap, "m"))
            window = alerts[(alerts >= floor) & (alerts < s)]
            if window.size:
                detected += 1
                leads.append((s - window.min()) / np.timedelta64(1, "m"))

    return {
        "events": n_events,
        "events_detected": detected,
        "event_pod": detected / n_events if n_events else 0.0,
        "median_lead_minutes": float(np.median(leads)) if leads else float("nan"),
        "p25_lead_minutes": float(np.percentile(leads, 25)) if leads else float("nan"),
        "horizon_h": horizon_h,
        "tier_cm": tier_cm,
    }


# ---------------------------------------------------------------------------
# Splits
# ---------------------------------------------------------------------------
def folds() -> List[Dict[str, object]]:
    """The rolling-origin folds from config, as plain dicts.

    Chronological, never shuffled. Neighbouring 5-minute readings are close to
    identical, so a random split puts near-copies of the test rows into training
    and inflates every score by 20-30 points. The result is indefensible in front
    of BMA and cannot be reproduced in production.
    """
    return [dict(f) for f in load_config()["splits"]["folds"]]


def embargo_mask(ts: pd.Series, boundary: pd.Timestamp,
                 hours: Optional[int] = None) -> np.ndarray:
    """True for rows far enough from a split boundary to be safe to use.

    Features look back 24 hours (`fl_max_24h`), so a row on 1 January contains
    readings from 31 December. Without an embargo the last day of training and
    the first day of testing share their inputs. The window is dropped from the
    TRAINING side, never the test side — shrinking the test set to make a score
    look better is the thing being guarded against.
    """
    hours = hours or load_config()["splits"]["embargo_hours"]
    ts = pd.to_datetime(ts)
    return (ts < boundary - pd.Timedelta(hours=hours)).to_numpy()


def scorable(df: pd.DataFrame, horizon_h: int) -> np.ndarray:
    """Rows whose forward window was observed well enough to be scored.

    A sensor that was offline for the next three hours has no label, not a
    negative one. Counting those rows as negatives is how a model learns that
    certain stations stopped flooding in 2023, and it silently improves every
    precision figure in the report.
    """
    return df[f"y_valid_{horizon_h}h"].fillna(False).to_numpy(dtype=bool)
