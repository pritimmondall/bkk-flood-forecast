"""
Training the models. Phase 4.

--------------------------------------------------------------------------
WHY GRADIENT-BOOSTED TREES AND NOT A TRANSFORMER
--------------------------------------------------------------------------
There are 837 flood events at the 15 cm tier in the entire seven-year archive.
Not per year — in total, for all of Bangkok. At the 30 cm tier a whole year
contains about 43 positive rows.

That number governs everything. A sequence model with millions of parameters has
nothing like enough events to learn from and will memorise station identities
instead. LightGBM handles missing values natively, trains in seconds, and its
splits can be read and argued with — which matters when the output becomes a
public alert. A sequence challenger is Phase 6, and it has to *beat* this to be
promoted.

--------------------------------------------------------------------------
THE THREE MODELS
--------------------------------------------------------------------------
  general      every row. Will be dominated by "is the road wet now", because
               that is where the rows are.
  onset        ONLY rows where the road is currently below the tier. This is the
               model that does forecasting rather than monitoring.
  depth        quantile regression on how deep it gets, for the p95 that decides
               the CAP severity level.

--------------------------------------------------------------------------
NEGATIVE DOWNSAMPLING, AND THE CORRECTION IT REQUIRES
--------------------------------------------------------------------------
Five training years is 17.6 million rows by 51 features — about 3.6 GB as
float32, on a machine that has already been OOM-killed twice in this project.

So every positive row is kept and negatives are sampled. This is safe for
ranking, which is what PR-AUC and threshold selection depend on, but it shifts
the predicted probabilities upward by a known factor. `correct_for_downsampling`
puts them back. Skip that step and the model will look badly over-confident the
first time anyone reads a probability off it — and a CAP message carries a
probability.
"""

from __future__ import annotations

import json
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .config import load_config, resolve
from .rawio import connect

# Set at import so a missing LightGBM is a clear error at call time, not a
# confusing ImportError halfway through a notebook.
try:                                    # pragma: no cover
    import lightgbm as lgb
except ImportError:                     # pragma: no cover
    lgb = None


# GFS forecast rain begins on this date. Any fold whose training years end before
# it has no forecast data at all, so those columns must be dropped rather than
# imputed — an imputed forecast is an invented one.
GFS_FIRST_YEAR = 2021


def feature_set(all_columns: Sequence[str], kind: str,
                train_years: Sequence[int]) -> List[str]:
    """Which columns this model is allowed to see.

    Two rules, both from measurement rather than preference:

    **`rain_fcst_*` goes to the onset model only.** Phase 3 measured it on all
    five forecast years: adding it improves onset PR-AUC by 24% (0.0055 → 0.0068)
    and *degrades* all-rows PR-AUC by 24% (0.0512 → 0.0389). It helps where
    forecasting is needed and adds noise where the current depth already answers
    the question. Giving it to the general model spends accuracy on rows that did
    not need it.

    **A fold that predates 23 March 2021 drops it entirely.** Fold 1 trains on
    2019–2020, where the column is 100% missing. Training on an all-NaN column
    teaches nothing; imputing it invents a forecast that was never made.

    **`era5_*` is excluded from every model, and this one cost something.**
    ERA5 is reanalysis: ECMWF publishes it roughly five days in arrears. In the
    feature table it is a perfectly legitimate record of past rain, and the model
    likes it — dropping `era5_rain_3h` takes the onset specialist from 0.160 to
    0.129 PR-AUC, a fifth of its performance.

    It is dropped anyway, because at serving time the column does not exist. The
    last three hours of ERA5 will not be published for another five days, so a
    live request gets NaN where training had a number. This is training/serving
    skew rather than leakage — no future information is used — but the effect on
    a deployed system is the same: an offline score that cannot be reproduced in
    production, discovered after somebody has already been shown it.

    0.129 is the honest number. 0.160 is a number about a world where the weather
    reanalysis arrives instantly.
    """
    from .features import feature_columns

    cols = feature_columns(pd.DataFrame(columns=list(all_columns)))
    has_gfs = max(train_years) >= GFS_FIRST_YEAR
    if kind != "onset" or not has_gfs:
        cols = [c for c in cols if not c.startswith("rain_fcst")]
    # Not available at serving time. See the docstring -- this is deliberate and
    # it costs real accuracy.
    cols = [c for c in cols if not c.startswith("era5_")]
    return cols


def build_matrix(years: Sequence[int], tier_cm: int, horizon_h: int,
                 kind: str = "general", negative_rate: float = 0.05,
                 con=None, seed: int = 0, columns: Optional[Sequence[str]] = None,
                 target: str = "binary"
                 ) -> Tuple[pd.DataFrame, np.ndarray, Dict[str, object]]:
    """Rows to train on, sampled in DuckDB so the full table never reaches pandas.

    Every positive is kept. Negatives are sampled at `negative_rate`. Rows whose
    forward window was not observed (`y_valid` false) are dropped entirely —
    they are unlabelled, not negative.

    For `kind="onset"` only rows where the station is currently BELOW the tier
    are kept. That is the whole point of the specialist: it never sees the easy
    rows, so it cannot win by learning to repeat the current reading.
    """
    paths = [str(resolve(f"data/features/features_{y}.parquet")) for y in years]
    y_col = f"y_ge{tier_cm}_{horizon_h}h"
    onset_col = f"is_onset_{tier_cm}_{horizon_h}h"

    owns = con is None
    con = con or connect()
    try:
        all_cols = [d[0] for d in con.execute(
            f"SELECT * FROM read_parquet({paths}) LIMIT 0").description]
        feats = list(columns) if columns else feature_set(all_cols, kind, years)

        where = [f"y_valid_{horizon_h}h", f"{y_col} IS NOT NULL"]
        if kind == "onset":
            where.append(onset_col)

        # `target="depth"` returns the deepest water in the forward window, in
        # cm, for the quantile models. Same rows, different question: not "will
        # it flood" but "how deep".
        y_expr = (f"{y_col}::INT" if target == "binary"
                  else f'"y_maxdepth_{horizon_h}h"::DOUBLE')
        sel = ", ".join([f'"{c}"' for c in feats]
                        + [f"{y_expr} AS y", "station_code", "ts"])
        # hash() is deterministic, so a re-run samples the same negatives and two
        # models are comparable. random() would not be.
        q = f"""
        SELECT {sel} FROM read_parquet({paths})
        WHERE {' AND '.join(where)}
          AND ({y_col} OR (hash(station_code || ts::VARCHAR || {seed}) % 1000000)
                            < {int(negative_rate * 1_000_000)})
        """
        df = con.execute(q).fetchdf()
    finally:
        if owns:
            con.close()

    y = df.pop("y").to_numpy(dtype=np.int8 if target == "binary" else "float64")
    meta = {
        "years": list(years), "tier_cm": tier_cm, "horizon_h": horizon_h,
        "kind": kind, "negative_rate": negative_rate,
        "rows": int(len(df)), "positives": int((y > 0).sum()), "target": target,
        "features": feats, "n_features": len(feats),
        "gfs_included": any(c.startswith("rain_fcst") for c in feats),
    }
    return df[feats], y, meta


def correct_for_downsampling(p: np.ndarray, negative_rate: float) -> np.ndarray:
    """Undo the probability shift that negative downsampling causes.

    Sampling negatives at rate r multiplies the odds by 1/r, so the fix is to
    multiply the odds back by r:

        odds_true = odds_sampled * r

    Ranking is unaffected — this is monotonic — so PR-AUC and any threshold
    chosen on the sampled data are unchanged. What changes is the number itself,
    and that number ends up inside a CAP message as a probability. A model
    trained at a 5% negative rate reports roughly twenty times the true risk if
    this step is skipped.
    """
    p = np.clip(np.asarray(p, dtype="float64"), 1e-12, 1 - 1e-12)
    odds = p / (1 - p) * negative_rate
    return odds / (1 + odds)


def train_classifier(X: pd.DataFrame, y: np.ndarray,
                     X_val: pd.DataFrame, y_val: np.ndarray,
                     params: Optional[Dict] = None, num_round: int = 2000,
                     early_stopping: int = 100, seed: int = 0):
    """Train one binary LightGBM, early-stopped on validation average precision.

    `average_precision` is the early-stopping metric, not AUC or log-loss. With
    1 positive in 9,000 rows, ROC-AUC is flattered by the enormous negative class
    and log-loss is minimised by predicting near-zero everywhere. Average
    precision has the positive class in both terms of every point on the curve.

    No `is_unbalance` or `scale_pos_weight` by default: negative downsampling has
    already rebalanced the data, and stacking a second correction on top pushes
    probabilities far from calibrated for no gain in ranking.
    """
    if lgb is None:                                        # pragma: no cover
        raise ImportError("pip install lightgbm")

    p = {
        "objective": "binary",
        "metric": "average_precision",
        "learning_rate": 0.05,
        "num_leaves": 63,
        "min_data_in_leaf": 100,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "lambda_l2": 1.0,
        "verbosity": -1,
        "seed": seed,
        "num_threads": load_config()["compute"]["threads"],
    }
    p.update(params or {})

    ds = lgb.Dataset(X, label=y, free_raw_data=False)
    dv = lgb.Dataset(X_val, label=y_val, reference=ds, free_raw_data=False)
    return lgb.train(p, ds, num_boost_round=num_round, valid_sets=[dv],
                     valid_names=["val"],
                     callbacks=[lgb.early_stopping(early_stopping, verbose=False),
                                lgb.log_evaluation(0)])


def train_quantile(X: pd.DataFrame, y: np.ndarray, X_val: pd.DataFrame,
                   y_val: np.ndarray, alpha: float, params: Optional[Dict] = None,
                   num_round: int = 1000, early_stopping: int = 80, seed: int = 0):
    """Quantile regression on how deep the water gets.

    A binary alert says "it will flood". An operations team also needs "how
    badly", and a single predicted depth is close to useless when the
    distribution is this skewed — the mean of a variable that is zero 99% of the
    time is not a depth anyone can act on.

    `alpha=0.95` gives the p95 depth that config maps to CAP severity levels.
    A 0.05/0.95 pair gives the 90% interval that `quantile_coverage_target`
    asks for, and coverage must then be CHECKED on the test year, not assumed:
    quantile models routinely miss their nominal rate on skewed data.
    """
    if lgb is None:                                        # pragma: no cover
        raise ImportError("pip install lightgbm")

    p = {
        "objective": "quantile", "alpha": alpha, "metric": "quantile",
        "learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 200,
        "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1,
        "verbosity": -1, "seed": seed,
        "num_threads": load_config()["compute"]["threads"],
    }
    p.update(params or {})
    ds = lgb.Dataset(X, label=y, free_raw_data=False)
    dv = lgb.Dataset(X_val, label=y_val, reference=ds, free_raw_data=False)
    return lgb.train(p, ds, num_boost_round=num_round, valid_sets=[dv],
                     callbacks=[lgb.early_stopping(early_stopping, verbose=False),
                                lgb.log_evaluation(0)])


def score_year(booster, year: int, features: Sequence[str], tier_cm: int,
               horizon_h: int, kind: str = "general", negative_rate: float = 1.0,
               con=None, chunk_rows: int = 750_000,
               full_population: bool = False) -> pd.DataFrame:
    """Predict a whole year, read in chunks, with the labels attached.

    `full_population=True` scores every scorable row even for an onset model,
    and is REQUIRED for event-level evaluation. An onset model is trained and
    row-scored only where the road is currently dry — but an event is defined by
    the water arriving, and those rows are exactly the ones that filter removes.
    Scoring the onset model on its own filtered frame yields zero events and an
    event POD of 0.0, which looks like total failure and is a measurement
    artefact.

    The honest construction is to score the whole year and then refuse to ALERT
    on non-onset rows, which `onset_alertable` marks.

    THE TEST YEAR IS NEVER DOWNSAMPLED. Training may drop negatives; scoring may
    not. Removing negatives from a test set removes false positives, which
    inflates precision — a mistake that produces a very good-looking table and no
    warning at all.

    Chunked because a year at full width is around 700 MB in pandas and the
    predictions have to sit alongside it.
    """
    path = str(resolve(f"data/features/features_{year}.parquet"))
    y_col = f"y_ge{tier_cm}_{horizon_h}h"
    onset_col = f"is_onset_{tier_cm}_{horizon_h}h"
    keep = ["station_code", "ts", "fl_depth_now", y_col, onset_col,
            f"y_maxdepth_{horizon_h}h"]
    sel = ", ".join([f'"{c}"' for c in features] + [f'"{c}"' for c in keep])
    where = f"y_valid_{horizon_h}h"
    if kind == "onset" and not full_population:
        where += f" AND {onset_col}"

    owns = con is None
    con = con or connect()
    try:
        n = con.execute(
            f"SELECT count(*) FROM '{path}' WHERE {where}").fetchone()[0]
        out = []
        for off in range(0, n, chunk_rows):
            d = con.execute(f"SELECT {sel} FROM '{path}' WHERE {where} "
                            f"LIMIT {chunk_rows} OFFSET {off}").fetchdf()
            if d.empty:
                break
            p = booster.predict(d[list(features)],
                                num_iteration=booster.best_iteration)
            d = d[keep].copy()
            d["score"] = p
            d["prob"] = (correct_for_downsampling(p, negative_rate)
                         if negative_rate < 1.0 else p)
            # An onset model may score every row, but it may only ACT on rows
            # where the road is currently dry. Anywhere else its opinion is
            # untrained and must not become an alert.
            d["onset_alertable"] = (d[onset_col].fillna(False)
                                    if kind == "onset" else True)
            out.append(d)
    finally:
        if owns:
            con.close()
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=keep)


def gain_importance(booster, top: int = 20) -> pd.DataFrame:
    """Which features the model actually used, by total split gain.

    Read this against the Phase 3 baselines rather than on its own. If the top of
    this table is dominated by `fl_depth_now` and its lags, the model has learned
    to repeat the current reading — which persistence already does for free, at
    100% recall on ongoing rows and 1% event POD.
    """
    imp = pd.DataFrame({
        "feature": booster.feature_name(),
        "gain": booster.feature_importance("gain"),
        "splits": booster.feature_importance("split"),
    })
    imp["gain_share"] = imp.gain / max(imp.gain.sum(), 1e-12)
    return imp.sort_values("gain", ascending=False).head(top).reset_index(drop=True)


def save_model(booster, meta: Dict, name: str) -> str:
    """Write the booster and its metadata side by side.

    The metadata is not optional bookkeeping: it records the exact feature list,
    the fold, and the negative sampling rate. Without that rate the saved
    probabilities cannot be corrected, and the model is unservable.
    """
    d = resolve("models")
    d.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(d / f"{name}.txt"),
                       num_iteration=booster.best_iteration)
    meta = {**meta, "best_iteration": int(booster.best_iteration or 0)}
    (d / f"{name}.json").write_text(json.dumps(meta, indent=2, default=str))
    return str(d / f"{name}.txt")


def run_fold(fold: Dict, tier_cm: int, horizon_h: int, kind: str = "general",
             negative_rate: Optional[float] = None, con=None,
             params: Optional[Dict] = None, save_as: Optional[str] = None
             ) -> Tuple[pd.DataFrame, object, Dict]:
    """Train on one fold and score its test year, honestly.

    The sequence matters and is easy to get wrong:

    1. train on the training years
    2. early-stop on the validation year
    3. choose the alert threshold on the **validation** year
    4. apply that threshold, unchanged, to the test year

    Step 3 is the one that gets skipped. Choosing a threshold on the test set is
    not leakage of data but leakage of the decision, and it is quietly worth
    several points of F2 that will not exist in production.

    Event metrics are computed on the FULL test population even for an onset
    model, with alerts suppressed on rows the onset model is not entitled to
    judge. See `score_year(full_population=...)` for why.
    """
    from .evaluate import (binary_metrics, by_onset, best_threshold, event_pod,
                           pr_auc, brier)

    if negative_rate is None:
        # Onset rows are already the rare, hard subset; thinning them further
        # throws away the signal the specialist exists to find.
        negative_rate = 0.25 if kind == "onset" else 0.05

    X, y, meta = build_matrix(fold["train"], tier_cm, horizon_h, kind,
                              negative_rate, con=con)
    Xv, yv, _ = build_matrix([fold["val"]], tier_cm, horizon_h, kind,
                             negative_rate, con=con, columns=meta["features"])
    booster = train_classifier(X, y, Xv, yv, params=params)

    val = score_year(booster, fold["val"], meta["features"], tier_cm, horizon_h,
                     kind=kind, negative_rate=negative_rate, con=con)
    y_val = val[f"y_ge{tier_cm}_{horizon_h}h"].fillna(False).to_numpy(bool)
    chosen = best_threshold(y_val, val["score"].to_numpy(), metric="f2")

    test = score_year(booster, fold["test"], meta["features"], tier_cm, horizon_h,
                      kind=kind, negative_rate=negative_rate, con=con,
                      full_population=True)
    y_col = f"y_ge{tier_cm}_{horizon_h}h"
    test["pred"] = ((test["score"].to_numpy() >= chosen["threshold"])
                    & test["onset_alertable"].to_numpy(dtype=bool))
    yt = test[y_col].fillna(False).to_numpy(bool)

    # Row metrics for an onset model are only meaningful on the rows it judges.
    judged = test["onset_alertable"].to_numpy(dtype=bool)
    m = binary_metrics(yt[judged], test["pred"].to_numpy()[judged])
    split = by_onset(yt[judged], test["pred"].to_numpy()[judged],
                     test[f"is_onset_{tier_cm}_{horizon_h}h"][judged]).set_index("subset")
    ev = event_pod(test, "fl_depth_now", "pred", tier_cm, horizon_h)

    row = {
        "model": kind, "tier_cm": tier_cm, "horizon_h": horizon_h,
        "test_year": fold["test"], "train_years": str(fold["train"]),
        "n_features": meta["n_features"], "gfs": meta["gfs_included"],
        "train_rows": meta["rows"], "train_positives": meta["positives"],
        "best_iteration": int(booster.best_iteration or 0),
        "threshold": chosen["threshold"],
        "pr_auc": pr_auc(yt[judged], test["score"].to_numpy()[judged]),
        "base_rate": float(yt[judged].mean()),
        "brier": brier(yt[judged], test["prob"].to_numpy()[judged]),
        **{k: m[k] for k in ("precision", "recall", "f1", "f2", "fnr", "tp", "fp",
                             "fn", "positives")},
        "recall_onset": split.loc["onset", "recall"],
        "recall_ongoing": split.loc["ongoing", "recall"],
        "events": ev["events"], "event_pod": ev["event_pod"],
        "median_lead_minutes": ev["median_lead_minutes"],
        "negative_rate": negative_rate,
    }
    if save_as:
        save_model(booster, {**meta, "threshold": chosen["threshold"],
                             "fold": fold}, save_as)
    return pd.DataFrame([row]), booster, meta
