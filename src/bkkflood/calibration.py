"""
Making the numbers mean what they say. Phase 5.

--------------------------------------------------------------------------
WHY THIS IS A SEPARATE PHASE
--------------------------------------------------------------------------
A model that ranks well is not the same as a model whose probabilities are
true. Ranking is all PR-AUC and threshold selection need, so a model can sail
through Phase 4 while its "0.30" means 0.03 in reality.

That stops mattering the moment a number leaves the notebook. CAP messages carry
a probability and a severity. An operations room reads "70% chance" as seventy
out of a hundred. If it is really seven, the system is not wrong once — it is
wrong in a way that trains people to ignore it.

--------------------------------------------------------------------------
THE THREE CHECKS HERE
--------------------------------------------------------------------------
  reliability_curve   do predicted probabilities match observed frequencies
  isotonic_fit        repair them, fitted on VALIDATION only
  quantile_coverage   does a "90% interval" actually contain the truth 90% of
                      the time — on wet rows, where it matters

--------------------------------------------------------------------------
THE TRAP IN CALIBRATING A RARE EVENT
--------------------------------------------------------------------------
At a base rate of 1 in 9,000, almost every predicted probability is near zero
and almost every one of them is correct. Equal-width bins put 99.99% of rows in
the first bin and report near-perfect calibration for a model that has learned
nothing.

So the bins here are **quantile bins on the predicted score**, not equal-width
bins on probability, and every curve is reported with the count in each bin
beside it. A bin holding four positives says nothing, however good its number.
"""

from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .config import load_config


def reliability_curve(y_true: np.ndarray, prob: np.ndarray, n_bins: int = 12,
                      strategy: str = "quantile") -> pd.DataFrame:
    """Predicted probability against observed frequency, bin by bin.

    `strategy="quantile"` puts an equal NUMBER of rows in each bin. The
    alternative — equal-width bins between 0 and 1 — is the standard choice and
    is useless here: at a 1-in-9,000 base rate it places essentially every row
    in the lowest bin and reports a flat, flattering curve.

    Returns the count and the positive count per bin, because a bin containing
    three positives cannot support any claim about calibration and the number
    alone will not say so.
    """
    y_true = np.asarray(y_true, dtype=bool)
    prob = np.asarray(prob, dtype="float64")
    keep = ~np.isnan(prob)
    y_true, prob = y_true[keep], prob[keep]
    if prob.size == 0:
        return pd.DataFrame()

    if strategy == "quantile":
        edges = np.unique(np.quantile(prob, np.linspace(0, 1, n_bins + 1)))
    else:
        edges = np.linspace(0, 1, n_bins + 1)
    if edges.size < 2:
        return pd.DataFrame()

    idx = np.clip(np.digitize(prob, edges[1:-1], right=True), 0, len(edges) - 2)
    rows = []
    for b in range(len(edges) - 1):
        m = idx == b
        if not m.any():
            continue
        rows.append({
            "bin": b,
            "lo": float(edges[b]), "hi": float(edges[b + 1]),
            "rows": int(m.sum()),
            "positives": int(y_true[m].sum()),
            "mean_predicted": float(prob[m].mean()),
            "observed_rate": float(y_true[m].mean()),
        })
    out = pd.DataFrame(rows)
    if len(out):
        out["gap"] = out.mean_predicted - out.observed_rate
        # Ratio is the readable version: 20 means "claims twenty times the truth".
        out["over_confidence"] = out.mean_predicted / out.observed_rate.replace(0, np.nan)
    return out


def expected_calibration_error(curve: pd.DataFrame) -> float:
    """Row-weighted mean absolute gap between predicted and observed.

    One number for the whole curve. Small ECE on a rare event is close to
    meaningless on its own — predicting the base rate everywhere achieves it —
    so read it beside `reliability_curve` rather than instead of it.
    """
    if curve.empty:
        return float("nan")
    w = curve["rows"] / curve["rows"].sum()
    return float((w * curve["gap"].abs()).sum())


def isotonic_fit(y_true: np.ndarray, prob: np.ndarray):
    """Fit a monotone probability correction on VALIDATION data.

    Isotonic regression rather than Platt scaling: it makes no assumption about
    the shape of the distortion, which matters because negative downsampling
    plus a rare event distorts the low end far more than the high end.

    Monotone by construction, so **ranking is unchanged** — every threshold, and
    therefore every recall and precision figure from Phase 4, survives
    untouched. Only the numbers move.

    Fitted on validation and applied to test. Fitting on test is the same
    mistake as tuning a threshold there: it makes the report better without
    making the system better.
    """
    from sklearn.isotonic import IsotonicRegression

    y_true = np.asarray(y_true, dtype="float64")
    prob = np.asarray(prob, dtype="float64")
    keep = ~np.isnan(prob)
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(prob[keep], y_true[keep])
    return iso


def apply_isotonic(iso, prob: np.ndarray) -> np.ndarray:
    p = np.asarray(prob, dtype="float64")
    out = np.full(p.shape, np.nan)
    keep = ~np.isnan(p)
    out[keep] = iso.predict(p[keep])
    return out


# ---------------------------------------------------------------------------
# Quantile intervals
# ---------------------------------------------------------------------------
def quantile_coverage(truth: np.ndarray, lo: np.ndarray, hi: np.ndarray,
                      wet_threshold_cm: float = 0.0) -> Dict[str, float]:
    """Does the interval contain the truth as often as it claims?

    Reported twice: over all rows, and over WET rows only.

    The all-rows figure is the one that will be quoted if it is allowed to be,
    and it is worthless. About 99% of rows are dry, so the interval `[0, 0]`
    covers them and coverage comes out at 0.998 for a model that has learned to
    say "no water" and nothing else. Phase 4's depth model scored exactly that,
    while covering 43% of the rows where water was actually present.

    Coverage on wet rows is the only number that describes the product.
    """
    truth = np.asarray(truth, dtype="float64")
    lo = np.asarray(lo, dtype="float64")
    hi = np.asarray(hi, dtype="float64")
    ok = ~(np.isnan(truth) | np.isnan(lo) | np.isnan(hi))
    inside = (truth >= lo - 1e-9) & (truth <= hi + 1e-9)
    wet = ok & (truth > wet_threshold_cm)

    return {
        "rows": int(ok.sum()),
        "coverage_all": float(inside[ok].mean()) if ok.any() else float("nan"),
        "wet_rows": int(wet.sum()),
        "coverage_wet": float(inside[wet].mean()) if wet.any() else float("nan"),
        "median_width_cm": float(np.median((hi - lo)[ok])) if ok.any() else float("nan"),
        "median_width_wet_cm": float(np.median((hi - lo)[wet])) if wet.any() else float("nan"),
        "mean_under_cm": float(np.mean((truth - hi)[wet & (truth > hi)]))
                          if (wet & (truth > hi)).any() else 0.0,
    }


def coverage_verdict(cov: Dict[str, float]) -> Dict[str, object]:
    """Pass or fail against the tolerance band in config, on WET rows.

    Failing high and failing low are not the same failure. An interval that is
    too wide is useless but honest. An interval that is too narrow understates
    how deep the water will get, and it will be believed — that is the direction
    that puts a crew in the wrong place.
    """
    cfg = load_config()["objective"]
    lo, hi = cfg["quantile_coverage_tolerance"]
    c = cov.get("coverage_wet", float("nan"))
    if np.isnan(c):
        state = "no wet rows to judge"
    elif c < lo:
        state = "FAIL — too narrow, understates depth (the dangerous direction)"
    elif c > hi:
        state = "fail — too wide, honest but uninformative"
    else:
        state = "pass"
    return {"target": cfg["quantile_coverage_target"], "band": [lo, hi],
            "coverage_wet": c, "verdict": state,
            "publishable_as_p95": bool(lo <= c <= hi)}


def lead_time_distribution(df: pd.DataFrame, depth_col: str, pred_col: str,
                           tier_cm: int, horizon_h: int,
                           station_col: str = "station_code",
                           ts_col: str = "ts") -> pd.DataFrame:
    """Every detected event's warning time, not just the median.

    Phase 4 reported a median lead of 15 minutes at every tier, horizon and
    fold, which is one modelling time step. A median that constant is either a
    real ceiling or an artefact of the cadence, and the two cannot be told apart
    from a median. The full distribution can: if the mass sits at exactly one
    step, the models are firing at the last possible moment; if there is a long
    tail, some floods are being caught usefully early and the median is hiding
    them.
    """
    cfg = load_config()
    gap = cfg["flood_event"]["merge_gap_minutes"]
    d = df[[station_col, ts_col, depth_col, pred_col]].dropna(subset=[depth_col])
    d = d.sort_values([station_col, ts_col])

    out = []
    for station, g in d.groupby(station_col, sort=False):
        wet = g[g[depth_col].to_numpy() >= tier_cm]
        if wet.empty:
            continue
        t = wet[ts_col].to_numpy()
        starts = t[np.r_[True, (np.diff(t) > np.timedelta64(gap, "m"))]]
        alerts = g.loc[g[pred_col].astype(bool), ts_col].to_numpy()
        for i, s in enumerate(starts):
            floor = s - np.timedelta64(horizon_h, "h")
            if i > 0:
                floor = max(floor, t[t < s].max() + np.timedelta64(gap, "m"))
            w = alerts[(alerts >= floor) & (alerts < s)]
            out.append({
                "station_code": station,
                "event_start": pd.Timestamp(s),
                "detected": bool(w.size),
                "lead_minutes": float((s - w.min()) / np.timedelta64(1, "m"))
                                if w.size else np.nan,
            })
    return pd.DataFrame(out)
