#!/usr/bin/env python3
"""Build the model-ready training set from Phase-0 Parquet.

Input:  data/parquet/{flood,rain,water,flow}/<year>.parquet  (from phase0_ingest.py)
Output: data/training/train.parquet, val.parquet, test.parquet
        data/training/features.json   (feature list + build config)

One output row = (flood station, anchor timestamp). Default anchor cadence
is every 15 minutes on the 5-min grid.

Labels (per horizon H in 1h/3h/6h, strictly future window (t, t+H]):
  y_maxdepth_{H}h        max flood depth (cm) in window (NaN if window all-null)
  y_ge{tier}_{H}h        1 if depth >= tier for >=2 consecutive 5-min steps
                         in the window (tiers 5/15/30cm), else 0
  y_valid_{H}h           fraction of non-null 5-min readings in the window

Features use ONLY data at or before t (no leakage):
  flood autoregressive   depth now, 1h/3h lags, 3h/24h rolling max, 1h mean,
                         hours since depth >=5cm (capped 72h)
  rain (district join)   same-prefix rain stations (verified: covers 100% of
                         flood districts): mean rf1hr/rf3hr/rf24hr, max rf1hr,
                         1h change in rf1hr
  water (citywide)       mean 1h rise of wl_in across network, share of
                         stations rising >5cm/h, share of stations offline
  flow (citywide)        mean flow, share of stations with negative flow,
                         share offline
  calendar               hour + day-of-year (sin/cos), monsoon flag (May-Oct)

Split (chronological, no shuffling): train = 2019-2023, val = 2024,
test = 2025. Override with --train-years/--val-years/--test-years.

Usage:
  python build_training_set.py                       # full build
  python build_training_set.py --years 2024          # single year (testing)

Requires: pandas >= 2.0, pyarrow >= 14, numpy. Peak RAM ~4-6GB (Water year).
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

STEP_MIN = 5                       # raw cadence, minutes
STEPS_1H = 60 // STEP_MIN          # 12


# ---------------------------------------------------------------------------
# Small numeric helpers (all operate on one station's chronological array)
# ---------------------------------------------------------------------------

def future_window_stats(depth: np.ndarray, h_steps: int,
                        tiers: list[float]) -> dict[str, np.ndarray]:
    """Max / tier-exceedance / valid-share over the strictly-future window
    (t, t+h_steps]. Windows truncated at the series end are computed over
    what remains."""
    n = len(depth)
    # pad so every position has a full window
    pad = np.full(h_steps, np.nan)
    d = np.concatenate([depth[1:], pad])            # d[i] = depth[i+1]
    win = np.lib.stride_tricks.sliding_window_view(d, h_steps)[:n]
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        fmax = np.nanmax(win, axis=1)
    valid = 1.0 - np.isnan(win).mean(axis=1)

    out = {"maxdepth": fmax, "valid": valid}
    # persistence rule: two consecutive 5-min readings >= tier, with both
    # readings inside the future window -> start index j in [t+1, t+h-1]
    pair_min = np.minimum(depth[:-1], depth[1:])    # pair_min[j]=min(d[j],d[j+1])
    for tier in tiers:
        hit = np.append((pair_min >= tier).astype(float), 0.0)   # length n
        f = np.concatenate([hit[1:], np.zeros(h_steps)])         # f[i]=hit[i+1]
        hwin = np.lib.stride_tricks.sliding_window_view(f, max(h_steps - 1, 1))[:n]
        out[f"ge{int(tier)}"] = (hwin.max(axis=1) > 0).astype(np.int8)
    return out


def rolling_stat(x: np.ndarray, w: int, fn) -> np.ndarray:
    """Trailing-window stat (window = last w steps incl. current), NaN-safe."""
    pad = np.full(w - 1, np.nan)
    xp = np.concatenate([pad, x])
    win = np.lib.stride_tricks.sliding_window_view(xp, w)
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        return fn(win, axis=1)


def hours_since_ge(depth: np.ndarray, tier: float, cap_h: float) -> np.ndarray:
    """Hours since depth was last >= tier, capped; cap if never."""
    out = np.empty(len(depth))
    last = -np.inf
    cap_steps = cap_h * STEPS_1H
    for i, v in enumerate(depth):
        if v >= tier:
            last = i
        out[i] = min(i - last, cap_steps)
    return out / STEPS_1H


# ---------------------------------------------------------------------------
# Per-source feature builders (each returns a frame indexed on join keys)
# ---------------------------------------------------------------------------

def load(parquet_dir: Path, ds: str, year: int, cols: list[str]) -> pd.DataFrame:
    path = parquet_dir / ds / f"{year}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} — run phase0_ingest.py first")
    df = pq.read_table(path, columns=cols).to_pandas()
    df["station_code"] = df["station_code"].astype(str)
    return df


def rain_district_features(parquet_dir: Path, year: int) -> pd.DataFrame:
    """Per (district-prefix, timestamp): rain aggregates + 1h intensity change."""
    r = load(parquet_dir, "rain", year,
             ["station_code", "site_timestamp", "rf1hr", "rf3hr", "rf24hr"])
    r["prefix"] = r["station_code"].str.split(".").str[1]
    g = (r.groupby(["prefix", "site_timestamp"], observed=True)
           .agg(rain_rf1hr_mean=("rf1hr", "mean"),
                rain_rf1hr_max=("rf1hr", "max"),
                rain_rf3hr_mean=("rf3hr", "mean"),
                rain_rf24hr_mean=("rf24hr", "mean"))
           .reset_index()
           .sort_values(["prefix", "site_timestamp"]))
    g["rain_rf1hr_delta1h"] = (
        g.groupby("prefix", observed=True)["rain_rf1hr_mean"].diff(STEPS_1H))
    return g


def water_city_features(parquet_dir: Path, year: int) -> pd.DataFrame:
    """Per timestamp: citywide canal rise indicators (datum-independent)."""
    w = load(parquet_dir, "water", year,
             ["station_code", "site_timestamp", "wl_in"])
    w = w.sort_values(["station_code", "site_timestamp"])
    w["rise1h"] = w.groupby("station_code", observed=True)["wl_in"].diff(STEPS_1H)
    g = (w.groupby("site_timestamp")
           .agg(water_rise1h_mean=("rise1h", "mean"),
                water_rising_share=("rise1h", lambda s: (s > 0.05).mean()),
                water_offline_share=("wl_in", lambda s: s.isna().mean()))
           .reset_index())
    return g


def flow_city_features(parquet_dir: Path, year: int) -> pd.DataFrame:
    """Per timestamp: citywide drainage-state indicators."""
    f = load(parquet_dir, "flow", year,
             ["station_code", "site_timestamp", "flow", "sensor_out"])
    g = (f.groupby("site_timestamp")
           .agg(flow_mean=("flow", "mean"),
                flow_negative_share=("flow", lambda s: (s < 0).mean()),
                flow_offline_share=("sensor_out", "mean"))
           .reset_index())
    return g


# ---------------------------------------------------------------------------
# Year builder
# ---------------------------------------------------------------------------

def build_year(parquet_dir: Path, year: int, cadence_min: int,
               horizons_h: list[int], tiers: list[float]) -> pd.DataFrame:
    print(f"[{year}] loading flood...")
    fl = load(parquet_dir, "flood", year,
              ["station_code", "site_timestamp", "flood"])
    fl = fl.sort_values(["station_code", "site_timestamp"])

    print(f"[{year}] rain/water/flow features...")
    rain = rain_district_features(parquet_dir, year)
    water = water_city_features(parquet_dir, year)
    flow = flow_city_features(parquet_dir, year)

    stride = cadence_min // STEP_MIN
    frames = []
    for code, grp in fl.groupby("station_code", observed=True, sort=True):
        depth = grp["flood"].to_numpy(dtype=float)
        ts = grp["site_timestamp"].to_numpy()
        n = len(depth)

        cols: dict[str, np.ndarray] = {}
        # ---- labels
        for h in horizons_h:
            st = future_window_stats(depth, h * STEPS_1H, tiers)
            cols[f"y_maxdepth_{h}h"] = st["maxdepth"]
            cols[f"y_valid_{h}h"] = st["valid"]
            for tier in tiers:
                cols[f"y_ge{int(tier)}_{h}h"] = st[f"ge{int(tier)}"]
        # ---- flood autoregressive features (NaN kept; LGBM handles natively)
        cols["fl_depth_now"] = depth
        cols["fl_depth_lag1h"] = np.concatenate([np.full(STEPS_1H, np.nan),
                                                 depth[:-STEPS_1H]])
        cols["fl_depth_lag3h"] = np.concatenate([np.full(3 * STEPS_1H, np.nan),
                                                 depth[:-3 * STEPS_1H]])
        cols["fl_max3h"] = rolling_stat(depth, 3 * STEPS_1H, np.nanmax)
        cols["fl_max24h"] = rolling_stat(depth, 24 * STEPS_1H, np.nanmax)
        cols["fl_mean1h"] = rolling_stat(depth, STEPS_1H, np.nanmean)
        cols["fl_hrs_since_5cm"] = hours_since_ge(
            np.nan_to_num(depth, nan=-1.0), 5.0, cap_h=72.0)

        sub = pd.DataFrame({"site_timestamp": ts, **cols})
        sub = sub.iloc[::stride]                    # downsample to anchors
        sub.insert(0, "station_code", code)
        frames.append(sub)

    out = pd.concat(frames, ignore_index=True)
    out["prefix"] = out["station_code"].str.split(".").str[1]

    # ---- joins (all sources share the 5-min grid, so exact-key joins)
    out = out.merge(rain, on=["prefix", "site_timestamp"], how="left")
    out = out.merge(water, on="site_timestamp", how="left")
    out = out.merge(flow, on="site_timestamp", how="left")

    # ---- calendar
    ts = out["site_timestamp"]
    hour = ts.dt.hour + ts.dt.minute / 60.0
    doy = ts.dt.dayofyear.astype(float)
    out["cal_hour_sin"] = np.sin(2 * np.pi * hour / 24)
    out["cal_hour_cos"] = np.cos(2 * np.pi * hour / 24)
    out["cal_doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    out["cal_doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    out["cal_monsoon"] = ts.dt.month.isin([5, 6, 7, 8, 9, 10]).astype(np.int8)

    # keep only anchors whose 1h-horizon label is at least partially observed
    out = out[out["y_valid_1h"] > 0].reset_index(drop=True)
    out["station_code"] = out["station_code"].astype("category")
    out["prefix"] = out["prefix"].astype("category")
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--parquet-dir", type=Path, default=Path("data/parquet"))
    ap.add_argument("--out-dir", type=Path, default=Path("data/training"))
    ap.add_argument("--years", nargs="+", type=int,
                    default=[2019, 2020, 2021, 2022, 2023, 2024, 2025])
    ap.add_argument("--train-years", nargs="+", type=int,
                    default=[2019, 2020, 2021, 2022, 2023])
    ap.add_argument("--val-years", nargs="+", type=int, default=[2024])
    ap.add_argument("--test-years", nargs="+", type=int, default=[2025])
    ap.add_argument("--cadence", type=int, default=15,
                    help="anchor cadence in minutes (multiple of 5)")
    ap.add_argument("--horizons", nargs="+", type=int, default=[1, 3, 6])
    ap.add_argument("--tiers", nargs="+", type=float, default=[5, 15, 30])
    args = ap.parse_args()

    if args.cadence % STEP_MIN:
        ap.error("--cadence must be a multiple of 5")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    split_of = {y: "train" for y in args.train_years}
    split_of |= {y: "val" for y in args.val_years}
    split_of |= {y: "test" for y in args.test_years}

    writers: dict[str, pq.ParquetWriter] = {}
    feature_cols: list[str] | None = None
    counts: dict[str, int] = {}

    try:
        for year in args.years:
            split = split_of.get(year)
            if split is None:
                print(f"[{year}] not in any split, skipping")
                continue
            df = build_year(args.parquet_dir, year, args.cadence,
                            args.horizons, args.tiers)
            if feature_cols is None:
                feature_cols = [c for c in df.columns
                                if not c.startswith("y_")
                                and c not in ("station_code", "prefix",
                                              "site_timestamp")]
            table = pa.Table.from_pandas(df, preserve_index=False)
            if split not in writers:
                writers[split] = pq.ParquetWriter(
                    args.out_dir / f"{split}.parquet", table.schema,
                    compression="zstd")
            writers[split].write_table(table)
            counts[split] = counts.get(split, 0) + len(df)
            pos = int(df[f"y_ge15_{args.horizons[0]}h"].sum())
            print(f"[{year}] {len(df):,} rows -> {split} "
                  f"(y_ge15_{args.horizons[0]}h positives: {pos:,})")
    finally:
        for w in writers.values():
            w.close()

    meta = {
        "features": feature_cols or [],
        "labels": [f"y_maxdepth_{h}h" for h in args.horizons]
                  + [f"y_ge{int(t)}_{h}h" for h in args.horizons
                     for t in args.tiers],
        "cadence_min": args.cadence,
        "horizons_h": args.horizons,
        "tiers_cm": args.tiers,
        "splits": {s: {"years": [y for y, sp in split_of.items() if sp == s],
                       "rows": counts.get(s, 0)} for s in set(split_of.values())},
        "notes": [
            "rain joined per district prefix (verified 100% flood coverage)",
            "water/flow are citywide aggregates until station coordinates exist",
            "labels use strictly-future windows; features use only t and earlier",
            "NaN features are expected (LightGBM handles natively); "
            "for NN models impute + add indicator",
        ],
    }
    (args.out_dir / "features.json").write_text(json.dumps(meta, indent=2))
    print(f"\nDone: {counts} -> {args.out_dir}/  (+features.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
