"""
The bar that every model must clear.

--------------------------------------------------------------------------
WHY THESE ARE COMPUTED BEFORE ANY MODEL IS TRAINED
--------------------------------------------------------------------------
A PR-AUC of 0.42 at a 1-in-1,291 base rate sounds excellent. Whether it IS
excellent depends entirely on what "predict exactly what is happening right
now" already achieves, and that number is uncomfortable: flood depth is
strongly autocorrelated at 15-minute spacing, so persistence alone recovers
most of the ongoing-flood rows for free.

Recording the baselines first means every later result arrives with something
beside it. Recording them afterwards means choosing which baseline to publish
after seeing the model's number, which is not the same activity.

--------------------------------------------------------------------------
THE FOUR
--------------------------------------------------------------------------
  persistence      "it will be as it is now" — the hardest to beat on ongoing
                   rows, and the reason recall must be split by onset
  climatology      this station, this hour of day, this month: how often has it
                   flooded historically. Fitted on TRAIN years only.
  rain_rule        alert when district rainfall crosses a fixed threshold — the
                   closest thing to what an operations team would do by hand,
                   and therefore the baseline BMA will actually care about
  always_negative  predicts nothing ever floods. Included because it scores
                   99.92% accuracy, which is the clearest possible statement of
                   why accuracy is not reported anywhere in this project.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

from .config import load_config
from .evaluate import binary_metrics, by_onset, pr_auc, brier, best_threshold


def persistence(df: pd.DataFrame, tier_cm: int) -> np.ndarray:
    """Score = current depth. Alerting on it means "it is flooded now".

    Returned as the raw depth rather than a 0/1 so it can be thresholded like
    any model score and compared on the same PR curve. NaN where the current
    reading is missing — a dead sensor makes no prediction, it does not predict
    "dry".
    """
    return df["fl_depth_now"].to_numpy(dtype="float64")


def climatology(years: Iterable[int], tier_cm: int, horizon_h: int,
                min_rows: int = 200, con=None) -> pd.DataFrame:
    """Historical flood frequency per station, hour of day and month.

    FITTED IN SQL, DIRECTLY FROM THE PARQUET. This is the only baseline that
    needs the training years at all, and by fold 4 that is six years — about 21
    million rows. Loading them into pandas to compute three group-bys got the
    process OOM-killed at 3.9 GB, so the whole fit happens in DuckDB and only
    the result (a few thousand rows) comes back.

    Fitted on the TRAIN years only. Fitting on all years and scoring on the test
    year would let the baseline see the future, and an inflated baseline is not
    a conservative error — it hides a genuine model improvement.

    Cells with fewer than `min_rows` observations fall back to the station's own
    overall rate, then to the global rate. Without that, a station with three
    observations in a given hour gets a rate of 0.33 and dominates the curve.
    """
    from .config import resolve
    from .rawio import connect as _connect

    y = f"y_ge{tier_cm}_{horizon_h}h"
    paths = [str(resolve(f"data/features/features_{yr}.parquet")) for yr in years]

    owns = con is None
    con = con or _connect()
    try:
        out = con.execute(f"""
        WITH d AS (
            SELECT station_code,
                   date_part('hour',  ts)::INT AS hour,
                   date_part('month', ts)::INT AS month,
                   ({y})::INT AS y
            FROM read_parquet({paths})
            WHERE y_valid_{horizon_h}h AND {y} IS NOT NULL
        ),
        g AS (SELECT avg(y) AS global_rate FROM d),
        st AS (SELECT station_code, avg(y) AS station_rate FROM d GROUP BY 1),
        cell AS (SELECT station_code, hour, month, avg(y) AS cell_rate,
                        count(*) AS size FROM d GROUP BY 1, 2, 3)
        SELECT c.station_code, c.hour, c.month, c.size,
               CASE WHEN c.size >= {min_rows} THEN c.cell_rate
                    ELSE coalesce(s.station_rate, g.global_rate) END AS rate,
               g.global_rate
        FROM cell c LEFT JOIN st s USING (station_code) CROSS JOIN g
        """).fetchdf()
    finally:
        if owns:
            con.close()
    return out


def apply_climatology(df: pd.DataFrame, table: pd.DataFrame,
                      global_rate: Optional[float] = None) -> np.ndarray:
    """Look up the fitted rate for each row. Unseen combinations get the global rate."""
    ts = pd.to_datetime(df["ts"])
    key = pd.DataFrame({"station_code": df["station_code"].to_numpy(),
                        "hour": ts.dt.hour.to_numpy(),
                        "month": ts.dt.month.to_numpy()})
    merged = key.merge(table, on=["station_code", "hour", "month"], how="left")
    fallback = global_rate if global_rate is not None else float(table.rate.mean())
    return merged["rate"].fillna(fallback).to_numpy(dtype="float64")


def rain_rule(df: pd.DataFrame, column: str = "rain_rf1hr_mean") -> np.ndarray:
    """Score = recent district rainfall. Threshold it to get an operational rule.

    This is the baseline that matters politically. "Send a crew when it has
    rained 30 mm in an hour" is roughly what gets done today, and a forecasting
    system that cannot beat it is not worth deploying, however good its PR-AUC
    looks next to a random classifier.
    """
    return df[column].to_numpy(dtype="float64")


def run_baselines(train_years: Iterable[int], test: pd.DataFrame, tier_cm: int,
                  horizon_h: int, threshold_source: pd.DataFrame,
                  con=None) -> pd.DataFrame:
    """Score every baseline on `test`, one row each.

    `train_years` is a list of YEARS, not a DataFrame: the training data is only
    ever needed to fit the climatology, which is done in SQL. Passing frames
    here is what ran the machine out of memory on fold 4.

    Thresholds are chosen on `threshold_source` — the validation year — and then
    applied unchanged to `test`. Picking the threshold on the test set is
    leakage of the decision rather than of the data, and it is quietly worth
    several points of F2 that will not exist in production.
    """
    y_col = f"y_ge{tier_cm}_{horizon_h}h"
    onset_col = f"is_onset_{tier_cm}_{horizon_h}h"
    valid = test[f"y_valid_{horizon_h}h"].fillna(False).to_numpy(dtype=bool)
    t = test.loc[valid]
    y = t[y_col].fillna(False).to_numpy(dtype=bool)
    # Left nullable on purpose: NULL means the current reading is missing, so
    # the row is neither an onset nor an ongoing flood. `by_onset` reports those
    # separately rather than assigning them to whichever subset looks better.
    onset = t[onset_col]

    clim_table = climatology(train_years, tier_cm, horizon_h, con=con)
    global_rate = float(clim_table.global_rate.iloc[0]) if len(clim_table) else 0.0
    tune = threshold_source
    tune_valid = tune[f"y_valid_{horizon_h}h"].fillna(False).to_numpy(dtype=bool)
    tv = tune.loc[tune_valid]
    y_tune = tv[y_col].fillna(False).to_numpy(dtype=bool)

    scorers = {
        "persistence": persistence,
        "climatology": lambda d, _: apply_climatology(d, clim_table, global_rate),
        "rain_rule": lambda d, _: rain_rule(d),
    }

    rows = []
    for name, fn in scorers.items():
        s_test = fn(t, tier_cm)
        s_tune = fn(tv, tier_cm)
        chosen = best_threshold(y_tune, s_tune, metric="f2")
        pred = np.nan_to_num(s_test, nan=-np.inf) >= chosen["threshold"]

        m = binary_metrics(y, pred)
        split = by_onset(y, pred, onset).set_index("subset")
        rows.append({
            "baseline": name,
            "tier_cm": tier_cm, "horizon_h": horizon_h,
            "threshold": chosen["threshold"],
            "pr_auc": pr_auc(y, s_test),
            **{k: m[k] for k in ("precision", "recall", "f1", "f2", "fnr",
                                 "tp", "fp", "fn", "positives")},
            "recall_onset": split.loc["onset", "recall"],
            "recall_ongoing": split.loc["ongoing", "recall"],
            "precision_onset": split.loc["onset", "precision"],
            "positives_onset": int(split.loc["onset", "positives"]),
            "rows_depth_unknown": int(split.loc["depth_unknown", "rows"]),
        })

    # Predicts nothing, ever. Kept in the table so the accuracy of a useless
    # model sits in the same report as everything else.
    m = binary_metrics(y, np.zeros_like(y, dtype=bool))
    rows.append({
        "baseline": "always_negative", "tier_cm": tier_cm, "horizon_h": horizon_h,
        "threshold": float("inf"), "pr_auc": float(y.mean()),
        **{k: m[k] for k in ("precision", "recall", "f1", "f2", "fnr",
                             "tp", "fp", "fn", "positives")},
        "recall_onset": 0.0, "recall_ongoing": 0.0, "precision_onset": 0.0,
        "positives_onset": int((y & onset.fillna(False).to_numpy(dtype=bool)).sum()),
        "rows_depth_unknown": int(onset.isna().sum()),
    })

    out = pd.DataFrame(rows)
    out["base_rate"] = float(y.mean())
    out["rows_scored"] = int(len(t))
    return out
