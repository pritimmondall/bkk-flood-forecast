#!/usr/bin/env python3
"""Phase-1 baseline training: persistence + LightGBM on the training set.

Trains, per (tier x horizon): a binary flood-risk classifier, and per
(quantile x horizon): a depth quantile regressor. Evaluates everything on
val (2024), compares against the persistence baseline, and saves models +
metrics.

Persistence baseline (the honesty floor): "flooded >= tier now -> flooded
>= tier at horizon"; depth now -> depth at horizon. Any model that can't
beat this is not learning anything useful.

Outputs (under --out-dir, default models/artifacts/):
  clf_ge{tier}_{h}h.txt          LightGBM boosters (risk head)
  reg_q{qq}_{h}h.txt             LightGBM boosters (depth head)
  metrics.json                   PR-AUC / F2 / precision / recall / pinball
                                 for every model + persistence comparison
  feature_importance.csv         gain importance per classifier

Usage:
  python models/train_baseline.py                    # full train (~30-60 min)
  python models/train_baseline.py --quick            # tier 15 only, 1h/6h
  python models/train_baseline.py --sample-frac 0.02 # fast smoke test

Requires: lightgbm >= 4.0, scikit-learn, pandas, pyarrow, numpy.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import pyarrow as pa
from sklearn.metrics import average_precision_score, fbeta_score

VALID_MIN = 0.8          # min share of observed 5-min readings in label window


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def load_split(path: Path, features: list[str], horizons: list[int],
               tiers: list[int], sample_frac: float | None) -> pd.DataFrame:
    label_cols = ([f"y_maxdepth_{h}h" for h in horizons]
                  + [f"y_valid_{h}h" for h in horizons]
                  + [f"y_ge{t}_{h}h" for h in horizons for t in tiers])
    cols = ["station_code", "site_timestamp"] + features + label_cols
    # cast float64 -> float32 in Arrow BEFORE materializing to pandas:
    # halves peak memory, and cm-scale precision loses nothing
    import pyarrow.parquet as pq
    table = pq.read_table(path, columns=cols)
    schema = pa.schema([
        pa.field(f.name, pa.float32()) if f.type == pa.float64() else f
        for f in table.schema])
    df = table.cast(schema).to_pandas(self_destruct=True)
    if sample_frac:
        df = df.sample(frac=sample_frac, random_state=42)
    df["station_code"] = df["station_code"].astype("category")
    return df


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def best_f2(y_true: np.ndarray, y_prob: np.ndarray) -> dict:
    """Sweep thresholds, return the best-F2 operating point."""
    best = {"f2": 0.0, "threshold": 0.5, "precision": 0.0, "recall": 0.0}
    for thr in np.unique(np.quantile(y_prob, np.linspace(0.5, 0.9999, 200))):
        pred = y_prob >= thr
        tp = int((pred & (y_true == 1)).sum())
        if tp == 0:
            continue
        prec = tp / pred.sum()
        rec = tp / (y_true == 1).sum()
        f2 = 5 * prec * rec / (4 * prec + rec)
        if f2 > best["f2"]:
            best = {"f2": round(f2, 4), "threshold": float(thr),
                    "precision": round(prec, 4), "recall": round(rec, 4)}
    return best


def pinball_loss(y_true: np.ndarray, y_pred: np.ndarray, q: float) -> float:
    diff = y_true - y_pred
    return float(np.mean(np.maximum(q * diff, (q - 1) * diff)))


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

NEG_FRAC = 0.05          # negatives kept per classifier (all positives kept)


def train_classifier(train: pd.DataFrame, val: pd.DataFrame,
                     features: list[str], tier: int, h: int,
                     out_dir: Path, quick: bool) -> dict:
    ycol, vcol = f"y_ge{tier}_{h}h", f"y_valid_{h}h"
    tr = train[train[vcol] >= VALID_MIN]
    va = val[val[vcol] >= VALID_MIN]

    # Negative downsampling: at a ~0.04% positive rate, training on all
    # negatives + a huge scale_pos_weight saturates probabilities and lets
    # early stopping kill the model after 1 tree (observed on the first full
    # run). Keep every positive, sample NEG_FRAC of negatives; ranking
    # metrics on the (untouched) val set are unaffected. NOTE: predicted
    # probabilities are inflated by ~1/NEG_FRAC — rank/threshold on val,
    # don't read them as calibrated risk.
    pos_mask = tr[ycol] == 1
    tr = pd.concat([tr[pos_mask],
                    tr[~pos_mask].sample(frac=NEG_FRAC, random_state=42)])
    ytr, yva = tr[ycol].to_numpy(), va[ycol].to_numpy()
    pos = ytr.sum()
    if pos < 20:
        return {"skipped": f"only {int(pos)} train positives"}

    ratio = float((len(ytr) - pos) / pos)
    params = dict(
        objective="binary", metric="average_precision",
        learning_rate=0.05, num_leaves=63, min_data_in_leaf=50,
        feature_fraction=0.9, bagging_fraction=0.8, bagging_freq=1,
        scale_pos_weight=min(ratio, 30.0),
        verbosity=-1, seed=42,
    )
    dtr = lgb.Dataset(tr[features], ytr,
                      categorical_feature=["station_code"])
    dva = lgb.Dataset(va[features], yva, reference=dtr)
    t0 = time.time()
    booster = lgb.train(params, dtr, num_boost_round=150 if quick else 800,
                        valid_sets=[dva],
                        callbacks=[lgb.early_stopping(150, verbose=False)])
    prob = booster.predict(va[features], num_iteration=booster.best_iteration)

    # persistence: flooded >= tier now -> positive
    pers = (va["fl_depth_now"].to_numpy() >= tier).astype(int)
    pers_tp = int(((pers == 1) & (yva == 1)).sum())
    pers_prec = pers_tp / max(pers.sum(), 1)
    pers_rec = pers_tp / max(yva.sum(), 1)
    pers_f2 = (5 * pers_prec * pers_rec / (4 * pers_prec + pers_rec)
               if pers_tp else 0.0)

    booster.save_model(str(out_dir / f"clf_ge{tier}_{h}h.txt"))
    imp = pd.Series(booster.feature_importance("gain"), index=features)
    return {
        "train_rows": len(tr), "train_positives": int(pos),
        "val_positives": int(yva.sum()),
        "pr_auc": round(float(average_precision_score(yva, prob)), 4),
        "best_f2_point": best_f2(yva, prob),
        "persistence": {"f2": round(pers_f2, 4),
                        "precision": round(pers_prec, 4),
                        "recall": round(pers_rec, 4)},
        "best_iteration": booster.best_iteration,
        "train_seconds": round(time.time() - t0, 1),
        "_importance": imp,
    }


def train_quantile(train: pd.DataFrame, val: pd.DataFrame,
                   features: list[str], q: float, h: int,
                   out_dir: Path, quick: bool) -> dict:
    ycol, vcol = f"y_maxdepth_{h}h", f"y_valid_{h}h"
    tr = train[(train[vcol] >= VALID_MIN) & train[ycol].notna()]
    va = val[(val[vcol] >= VALID_MIN) & val[ycol].notna()]

    params = dict(
        objective="quantile", alpha=q, metric="quantile",
        learning_rate=0.05, num_leaves=63, min_data_in_leaf=200,
        feature_fraction=0.9, bagging_fraction=0.8, bagging_freq=1,
        verbosity=-1, seed=42,
    )
    dtr = lgb.Dataset(tr[features], tr[ycol],
                      categorical_feature=["station_code"])
    dva = lgb.Dataset(va[features], va[ycol], reference=dtr)
    booster = lgb.train(params, dtr, num_boost_round=150 if quick else 400,
                        valid_sets=[dva],
                        callbacks=[lgb.early_stopping(50, verbose=False)])
    pred = booster.predict(va[features], num_iteration=booster.best_iteration)
    yva = va[ycol].to_numpy()
    # persistence: depth stays as-is (treat unknown current depth as 0)
    pers = np.nan_to_num(va["fl_depth_now"].to_numpy(), nan=0.0)

    qq = f"{int(q * 100):02d}"
    booster.save_model(str(out_dir / f"reg_q{qq}_{h}h.txt"))
    return {
        "pinball": round(pinball_loss(yva, pred, q), 4),
        "pinball_persistence": round(pinball_loss(yva, pers, q), 4),
        "coverage": round(float((yva <= pred).mean()), 4),  # target ~= q
        "best_iteration": booster.best_iteration,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--training-dir", type=Path, default=Path("data/training"))
    ap.add_argument("--out-dir", type=Path, default=Path("models/artifacts"))
    ap.add_argument("--horizons", nargs="+", type=int, default=[1, 3, 6])
    ap.add_argument("--tiers", nargs="+", type=int, default=[5, 15, 30])
    ap.add_argument("--quantiles", nargs="+", type=float,
                    default=[0.05, 0.25, 0.50, 0.75, 0.95])
    ap.add_argument("--sample-frac", type=float, default=None,
                    help="subsample rows for a fast smoke test")
    ap.add_argument("--quick", action="store_true",
                    help="tier 15 only, horizons 1h/6h, fewer rounds")
    args = ap.parse_args()

    if args.quick:
        args.tiers, args.horizons = [15], [1, 6]

    meta = json.loads((args.training_dir / "features.json").read_text())
    features = meta["features"] + ["station_code"]
    args.out_dir.mkdir(parents=True, exist_ok=True)

    print("loading train/val...")
    train = load_split(args.training_dir / "train.parquet", meta["features"],
                       args.horizons, args.tiers, args.sample_frac)
    val = load_split(args.training_dir / "val.parquet", meta["features"],
                     args.horizons, args.tiers, args.sample_frac)
    print(f"train {len(train):,} rows | val {len(val):,} rows")

    metrics: dict = {"config": {k: str(v) for k, v in vars(args).items()},
                     "classifiers": {}, "quantile_regressors": {}}
    importances = {}

    for h in args.horizons:
        for tier in args.tiers:
            name = f"ge{tier}_{h}h"
            print(f"[clf {name}]", end=" ", flush=True)
            res = train_classifier(train, val, features, tier, h,
                                   args.out_dir, args.quick)
            imp = res.pop("_importance", None)
            if imp is not None:
                importances[name] = imp
            metrics["classifiers"][name] = res
            print(res.get("skipped") or
                  f"PR-AUC {res['pr_auc']} | F2 {res['best_f2_point']['f2']} "
                  f"(persistence F2 {res['persistence']['f2']})")
        for q in args.quantiles:
            name = f"q{int(q * 100):02d}_{h}h"
            print(f"[reg {name}]", end=" ", flush=True)
            res = train_quantile(train, val, features, q, h,
                                 args.out_dir, args.quick)
            metrics["quantile_regressors"][name] = res
            print(f"pinball {res['pinball']} "
                  f"(persistence {res['pinball_persistence']})")

    (args.out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    if importances:
        pd.DataFrame(importances).to_csv(args.out_dir / "feature_importance.csv")
    print(f"\nDone -> {args.out_dir}/ (models, metrics.json, "
          f"feature_importance.csv)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
