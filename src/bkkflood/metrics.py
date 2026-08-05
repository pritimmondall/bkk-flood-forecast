"""Every number that goes in the report is computed here.

The evaluator asked for precision, recall, F1, false-negative rate, and a
false-positive / false-negative analysis. This module produces all of them from
one place, so the notebooks, the final report and the API can never disagree
about what "recall" meant.

Three levels of scoring, and they answer different questions
------------------------------------------------------------
* **Row level** — "of all the 15-minute prediction rows, how many did we get
  right?" Easy to compute, but it over-weights long floods: a six-hour flood
  contributes 24 rows and a 20-minute one contributes 1.

* **Event level** — "of all the real flood episodes, how many did we warn
  about at all, and how early?" This is what an operator actually cares about,
  and it is the number to put in front of BMA.

* **Onset level** — row level, restricted to rows where the station was not
  already flooded. This is the honest measure of forecasting skill.

A note on false negatives
-------------------------
False-negative rate = FN / (FN + TP) = 1 - recall. We report it explicitly
because "recall 0.55" and "we miss 45% of floods" land very differently on a
reader, and the second one is the truth.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

try:  # scikit-learn is required, but keep the import failure readable
    from sklearn.metrics import average_precision_score, roc_auc_score
except ImportError:  # pragma: no cover
    average_precision_score = roc_auc_score = None  # type: ignore


# ===========================================================================
# Row-level classification
# ===========================================================================

@dataclass
class ConfusionCounts:
    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def n(self) -> int:
        return self.tp + self.fp + self.fn + self.tn

    @property
    def positives(self) -> int:
        return self.tp + self.fn

    @property
    def alarms(self) -> int:
        return self.tp + self.fp


def confusion(y_true: np.ndarray, y_pred: np.ndarray) -> ConfusionCounts:
    """Plain counts. `y_pred` must already be 0/1 (threshold applied)."""
    t = np.asarray(y_true).astype(bool)
    p = np.asarray(y_pred).astype(bool)
    return ConfusionCounts(
        tp=int(np.sum(t & p)),
        fp=int(np.sum(~t & p)),
        fn=int(np.sum(t & ~p)),
        tn=int(np.sum(~t & ~p)),
    )


def _safe(numerator: float, denominator: float) -> float:
    """Divide, returning 0.0 rather than NaN when nothing was predicted."""
    return float(numerator / denominator) if denominator else 0.0


def classification_metrics(y_true: np.ndarray, y_pred: np.ndarray,
                           y_score: np.ndarray | None = None) -> dict:
    """Precision, recall, F1, F2, FNR, FPR and friends, from hard predictions.

    Pass `y_score` (the continuous model output) as well to also get
    threshold-free metrics: PR-AUC, ROC-AUC and the Brier score.
    """
    c = confusion(y_true, y_pred)

    precision = _safe(c.tp, c.tp + c.fp)
    recall = _safe(c.tp, c.tp + c.fn)            # = probability of detection
    specificity = _safe(c.tn, c.tn + c.fp)
    fnr = _safe(c.fn, c.tp + c.fn)               # = 1 - recall, the miss rate
    fpr = _safe(c.fp, c.fp + c.tn)
    f1 = _safe(2 * precision * recall, precision + recall)
    f2 = _safe(5 * precision * recall, 4 * precision + recall)

    out = {
        "n_rows": c.n,
        "positives": c.positives,
        "alarms": c.alarms,
        "tp": c.tp, "fp": c.fp, "fn": c.fn, "tn": c.tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "f2": round(f2, 4),
        "false_negative_rate": round(fnr, 4),
        "false_positive_rate": round(fpr, 6),
        "specificity": round(specificity, 4),
        # How many alarms for each real event — the number operators complain
        # about. 4.0 means three false alarms for every true one.
        "alarms_per_hit": round(_safe(c.alarms, c.tp), 2),
        # Critical Success Index, standard in operational hydrology.
        "csi": round(_safe(c.tp, c.tp + c.fp + c.fn), 4),
    }

    if y_score is not None and average_precision_score is not None:
        s = np.asarray(y_score, dtype=float)
        t = np.asarray(y_true).astype(int)
        if t.min() != t.max():          # AUC is undefined for a single class
            out["pr_auc"] = round(float(average_precision_score(t, s)), 4)
            out["roc_auc"] = round(float(roc_auc_score(t, s)), 4)
        out["base_rate"] = round(float(t.mean()), 6)
        if s.min() >= 0.0 and s.max() <= 1.0:
            out["brier"] = round(float(np.mean((s - t) ** 2)), 6)
    return out


# ===========================================================================
# Threshold selection — done on validation data only, never on test
# ===========================================================================

def threshold_sweep(y_true: np.ndarray, y_score: np.ndarray,
                    n_points: int = 200) -> pd.DataFrame:
    """Metrics at many candidate cut-offs. One row per threshold.

    Thresholds are taken from the score quantiles rather than a uniform grid,
    because model scores bunch up near zero and a uniform grid would waste
    almost every point on the empty part of the range.

    **The quantiles must be dense in the upper tail**, which is a stronger
    requirement than it first appears. Spacing them uniformly by *rank* —
    `linspace(0, 1, 200)` — puts the top two candidates at the 99.5th percentile
    and the maximum, with nothing in between. At the base rates this project
    deals with (1 positive in 3,000 rows at 15 cm, 1 in 11,000 on a quiet year)
    the best operating point sits near the 99.99th percentile, so a rank-uniform
    grid cannot see it at all and `pick_threshold` is left choosing the least-bad
    option from a candidate set that excludes every good one. Measured on
    fold 4: the rank-uniform grid returned F2 0.18 where 0.44 was available from
    the same booster.

    So half the budget goes below the 99th percentile, and the rest is spaced
    logarithmically between there and the single highest-scoring row. That
    adapts to the size of the input instead of assuming a base rate.
    """
    s = np.asarray(y_score, dtype=float)
    t = np.asarray(y_true).astype(int)
    n_lo = max(1, n_points // 2)
    n_hi = max(1, n_points - n_lo)
    lo = np.linspace(0.0, 0.99, n_lo, endpoint=False)
    # 0.99 -> 1 - 1/len(s): the top candidate isolates the highest-scoring row.
    hi = 1.0 - np.logspace(-2.0, np.log10(1.0 / max(len(s), 2)), n_hi)
    qs = np.unique(np.quantile(s, np.clip(np.concatenate([lo, hi]), 0.0, 1.0)))
    rows = []
    for thr in qs:
        m = classification_metrics(t, s >= thr)
        m["threshold"] = float(thr)
        rows.append(m)
    return pd.DataFrame(rows)


def pick_threshold(y_true: np.ndarray, y_score: np.ndarray,
                   objective: str = "f2",
                   max_fnr: float | None = None,
                   min_precision: float | None = None,
                   n_points: int = 200) -> dict:
    """Choose the operating point.

    The rule, in order:
      1. Keep only thresholds that satisfy the hard constraints (a ceiling on
         the miss rate, a floor on precision).
      2. Among those, take the one that maximises the objective (F2 by
         default — it weights recall twice as heavily as precision, which is
         right when a missed flood costs more than a wasted patrol).
      3. If nothing satisfies the constraints, say so honestly in
         `constraints_met` and fall back to the plain objective maximum.

    Returns the chosen threshold plus its full metric row.
    """
    sweep = threshold_sweep(y_true, y_score, n_points)
    feasible = sweep
    if max_fnr is not None:
        feasible = feasible[feasible["false_negative_rate"] <= max_fnr]
    if min_precision is not None:
        feasible = feasible[feasible["precision"] >= min_precision]

    met = len(feasible) > 0
    pool = feasible if met else sweep
    best = pool.loc[pool[objective].idxmax()].to_dict()
    best["constraints_met"] = met
    best["objective"] = objective
    return best


# ===========================================================================
# Onset decomposition — the honesty check
# ===========================================================================

def decompose_by_onset(y_true: np.ndarray, y_pred: np.ndarray,
                       is_onset: np.ndarray,
                       y_score: np.ndarray | None = None) -> dict:
    """Split any metric set into 'already flooded' vs 'genuine onset'.

    Read the result like this: `overall.recall` is what a headline number would
    claim, `onset.recall` is what the model can actually forecast, and
    `ongoing.recall` is what a one-line persistence rule would have got for
    free. A large gap between the first two means the headline is misleading.
    """
    onset = np.asarray(is_onset).astype(bool)
    result = {
        "overall": classification_metrics(y_true, y_pred, y_score),
        "onset": classification_metrics(
            np.asarray(y_true)[onset], np.asarray(y_pred)[onset],
            None if y_score is None else np.asarray(y_score)[onset]),
        "ongoing": classification_metrics(
            np.asarray(y_true)[~onset], np.asarray(y_pred)[~onset],
            None if y_score is None else np.asarray(y_score)[~onset]),
    }
    result["onset_recall_gap"] = round(
        result["overall"]["recall"] - result["onset"]["recall"], 4)
    return result


# ===========================================================================
# Event-level scoring — what an operator experiences
# ===========================================================================

def event_scores(events: pd.DataFrame,
                 alarms: pd.DataFrame,
                 horizon_h: float,
                 tolerance_min: float = 30.0) -> dict:
    """Score whole flood episodes instead of individual rows.

    An event counts as **caught** if the model raised an alarm for that station
    at any time in the window [start - horizon - tolerance, start + tolerance].
    In words: we forecast it, or we at least noticed it as it began.

    `lead_time_minutes` is measured from the *earliest* qualifying alarm to the
    event start, so it answers "how much warning did people get?".

    Parameters
    ----------
    events : columns station_code, start (from labels.find_events_frame).
    alarms : columns station_code, site_timestamp — rows where the model fired.
    horizon_h : the forecast lead time the model was trained for.
    """
    if events.empty:
        return {"events": 0, "caught": 0, "pod": 0.0, "far": 0.0, "csi": 0.0,
                "median_lead_minutes": None, "alarms": int(len(alarms))}

    tol = pd.Timedelta(minutes=tolerance_min)
    horizon = pd.Timedelta(hours=horizon_h)

    alarms_by_station: dict[str, np.ndarray] = {
        str(code): np.sort(pd.to_datetime(grp["site_timestamp"]).to_numpy())
        for code, grp in alarms.groupby("station_code", observed=True)
    } if len(alarms) else {}

    caught, lead_times, matched_alarm_count = 0, [], 0
    for _, ev in events.iterrows():
        times = alarms_by_station.get(str(ev["station_code"]))
        if times is None or len(times) == 0:
            continue
        start = pd.Timestamp(ev["start"])
        lo = np.datetime64(start - horizon - tol)
        hi = np.datetime64(start + tol)
        window = times[(times >= lo) & (times <= hi)]
        if len(window):
            caught += 1
            matched_alarm_count += len(window)
            lead_times.append((start - pd.Timestamp(window[0])).total_seconds() / 60.0)

    n_events = int(len(events))
    n_alarms = int(len(alarms))
    pod = caught / n_events                                  # probability of detection
    # False-alarm ratio: the share of alarms that never lined up with an event.
    far = _safe(n_alarms - matched_alarm_count, n_alarms)
    csi = _safe(caught, caught + (n_events - caught) + (n_alarms - matched_alarm_count))

    return {
        "events": n_events,
        "caught": caught,
        "missed": n_events - caught,
        "pod": round(pod, 4),
        "far": round(far, 4),
        "csi": round(csi, 4),
        "alarms": n_alarms,
        "median_lead_minutes": round(float(np.median(lead_times)), 1) if lead_times else None,
        "mean_lead_minutes": round(float(np.mean(lead_times)), 1) if lead_times else None,
    }


# ===========================================================================
# Per-station breakdown and case extraction (the FP / FN analysis)
# ===========================================================================

def per_station_breakdown(df: pd.DataFrame, y_col: str, pred_col: str,
                          station_col: str = "station_code") -> pd.DataFrame:
    """Metrics for each station, worst misses first.

    Use this to find the handful of stations that generate most of the errors.
    In practice a small number of sites dominate, and they usually have a
    physical explanation (a pump, a tidal gate, a broken sensor) that no amount
    of model tuning will fix.
    """
    rows = []
    for code, grp in df.groupby(station_col, observed=True):
        m = classification_metrics(grp[y_col].to_numpy(), grp[pred_col].to_numpy())
        m["station_code"] = str(code)
        rows.append(m)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    cols = ["station_code", "positives", "tp", "fn", "fp",
            "recall", "precision", "f2", "false_negative_rate"]
    out = out[cols + [c for c in out.columns if c not in cols]]
    return out.sort_values(["fn", "positives"], ascending=[False, False]).reset_index(drop=True)


def extract_cases(df: pd.DataFrame, y_col: str, pred_col: str,
                  score_col: str | None = None, kind: str = "fn",
                  top_n: int = 20,
                  context_cols: Sequence[str] = ()) -> pd.DataFrame:
    """Pull out the worst individual mistakes so a human can read them.

    kind="fn" gives the misses the model was most confident were safe — these
    are the ones worth investigating one by one. kind="fp" gives the loudest
    false alarms.
    """
    y = df[y_col].to_numpy().astype(bool)
    p = df[pred_col].to_numpy().astype(bool)
    mask = (y & ~p) if kind == "fn" else (~y & p)
    sub = df.loc[mask].copy()
    if score_col and score_col in sub.columns:
        sub = sub.sort_values(score_col, ascending=(kind == "fn"))
    keep = [c for c in (["station_code", "site_timestamp", y_col, pred_col,
                         score_col, *context_cols]) if c and c in sub.columns]
    return sub[keep].head(top_n).reset_index(drop=True)


# ===========================================================================
# Regression / uncertainty scoring
# ===========================================================================

def pinball_loss(y_true: np.ndarray, y_pred: np.ndarray, quantile: float) -> float:
    """Loss for a quantile forecast. Lower is better.

    It penalises under-prediction and over-prediction asymmetrically, in the
    proportion the quantile implies — so a P95 model is punished hard for
    predicting too low, which is exactly the behaviour we want for a flood
    depth upper bound.
    """
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_pred, dtype=float)
    ok = np.isfinite(y) & np.isfinite(p)
    if not ok.any():
        return float("nan")
    diff = y[ok] - p[ok]
    return float(np.mean(np.maximum(quantile * diff, (quantile - 1) * diff)))


def coverage(y_true: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> float:
    """Share of true values that fall inside the predicted band.

    A well-calibrated 5th-to-95th percentile band should contain about 90% of
    the truth. Much less means the band is too narrow and the dashboard is
    understating risk.
    """
    y, lo, hi = (np.asarray(a, dtype=float) for a in (y_true, lower, upper))
    ok = np.isfinite(y) & np.isfinite(lo) & np.isfinite(hi)
    return float(np.mean((y[ok] >= lo[ok]) & (y[ok] <= hi[ok]))) if ok.any() else float("nan")


# ===========================================================================
# Formatting
# ===========================================================================

def metrics_table(results: Iterable[dict],
                  order: Sequence[str] = ("target", "horizon_h", "model",
                                          "positives", "precision", "recall",
                                          "f1", "f2", "false_negative_rate",
                                          "pr_auc")) -> pd.DataFrame:
    """Stack many metric dicts into the tidy table that goes in the report."""
    df = pd.DataFrame(list(results))
    front = [c for c in order if c in df.columns]
    return df[front + [c for c in df.columns if c not in front]]
