"""Turning clean sensor data into model inputs, without leaking the future.

The one rule
------------
A feature at time *t* may only use data recorded at or before *t*. Every
rolling window here is trailing. Every lag is backwards. If you add a feature,
check it against this rule first — a leak produces a beautiful validation score
and a model that fails the moment it meets real time.

What we build, and why
----------------------
**Flood autoregressive** (`fl_*`) — where the water is right now and where it
has been. These dominate the short horizon and they should: if a road is
already 20 cm deep, the best guess for an hour from now is "still deep". The
danger is that a model leans on them so hard it never learns anything else,
which is exactly what happened in v1. The onset models in
`notebooks/05` exist to break that habit.

**Rain** (`rain_*`) — joined by district code prefix. Rain station codes and
flood station codes share a district prefix, and that prefix covers 100% of
flood districts (verified). This is the only real spatial join available until
station coordinates arrive.

*The known weakness*: this is a district **average**. Bangkok floods from
small, intense convective cells that can dump 40 mm on one sub-district and
nothing two kilometres away. Averaging over a district smears exactly the
signal we need. Radar rainfall is the single highest-value missing input.

**Water and flow** (`water_*`, `flow_*`) — citywide aggregates only. Their
station codes are canal-based, not district-based, so they cannot be joined to
a flood station without coordinates. Aggregates still carry real information
("the canal network as a whole is rising") but they are blunt.

**Forecast rain** (`rain_fcst_*`) — rainfall that has not fallen yet, from a
weather model. Measured to be about three times more predictive of a 6-hour
flood than past rain, which stands to reason: past rain cannot tell you about a
storm that has not arrived. Optional; joined if the file exists.

**Terrain** (`elev_m`, `slope_deg`, ...) — from the digital elevation model.
Tested weak so far, because 31 m SRTM cannot see a street-level dip and the
station identity already encodes most of it. Kept because LiDAR would make
them work.

**Calendar and tide** (`cal_*`, `tide_*`) — hour of day, day of year, monsoon
flag, and a tidal phase proxy. The Chao Phraya is tidal, and a high tide holds
the drainage gates shut, so heavy rain at high tide floods when the same rain
at low tide drains away. We have no tide gauge, so we reconstruct the phase
from the known lunar periods. It costs nothing and it is real physics.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from .config import CFG, PATHS, steps_per_hour, anchor_stride, tier_values
from .labels import future_window_labels, onset_mask

STEPS_1H = steps_per_hour()          # 12 readings per hour at 5-minute cadence


# ===========================================================================
# Low-level array helpers
# ===========================================================================

def trailing(x: np.ndarray, window_steps: int, fn: Callable) -> np.ndarray:
    """Rolling statistic over the last `window_steps` readings, including now.

    Trailing, never centred, never forward — that is what makes it leak-free.
    The first few positions are padded with NaN because there is no history yet.
    """
    w = max(1, int(window_steps))
    padded = np.concatenate([np.full(w - 1, np.nan), np.asarray(x, dtype=float)])
    windows = np.lib.stride_tricks.sliding_window_view(padded, w)
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        return fn(windows, axis=1)


def lag(x: np.ndarray, steps: int) -> np.ndarray:
    """Value from `steps` readings ago; NaN where there is no history."""
    s = max(0, int(steps))
    x = np.asarray(x, dtype=float)
    return np.concatenate([np.full(s, np.nan), x[:len(x) - s]]) if s else x.copy()


def hours_since_above(x: np.ndarray, threshold: float,
                      cap_hours: float = 72.0) -> np.ndarray:
    """How long since this series was last at or above `threshold`.

    Capped, so "never in living memory" and "not for four days" look the same
    to the model instead of producing a meaningless huge number. Missing values
    are treated as 'not above'.
    """
    x = np.nan_to_num(np.asarray(x, dtype=float), nan=-np.inf)
    cap_steps = cap_hours * STEPS_1H
    out = np.empty(len(x))
    last = -np.inf
    for i, v in enumerate(x):
        if v >= threshold:
            last = i
        out[i] = min(i - last, cap_steps)
    return out / STEPS_1H


# ===========================================================================
# Flood station features (per station, chronological)
# ===========================================================================

def flood_features(depth: np.ndarray) -> dict[str, np.ndarray]:
    """Autoregressive features from one station's depth series (centimetres)."""
    d = np.asarray(depth, dtype=float)
    return {
        "fl_depth_now": d,
        "fl_depth_lag1h": lag(d, STEPS_1H),
        "fl_depth_lag3h": lag(d, 3 * STEPS_1H),
        # Rate of change: is the water climbing or draining right now?
        "fl_rise_15min": d - lag(d, 3),
        "fl_rise_1h": d - lag(d, STEPS_1H),
        "fl_max3h": trailing(d, 3 * STEPS_1H, np.nanmax),
        "fl_max24h": trailing(d, 24 * STEPS_1H, np.nanmax),
        "fl_mean1h": trailing(d, STEPS_1H, np.nanmean),
        "fl_std3h": trailing(d, 3 * STEPS_1H, np.nanstd),
        "fl_hrs_since_5cm": hours_since_above(d, 5.0, cap_hours=72.0),
        "fl_hrs_since_15cm": hours_since_above(d, 15.0, cap_hours=168.0),
        # A missing reading is itself informative: sensors often drop out
        # during the worst weather, so an outage is weak evidence of trouble.
        "fl_missing_share3h": trailing(np.isnan(d).astype(float),
                                       3 * STEPS_1H, np.nanmean),
    }


# ===========================================================================
# Rain features (district prefix join)
# ===========================================================================

def rain_district_features(year: int, parquet_dir: Path | None = None) -> pd.DataFrame:
    """Rain aggregates per (district prefix, timestamp).

    Station codes look like `RN.BKN.02`; the middle token is the district. Flood
    codes use the same scheme, so the prefix is our spatial join.
    """
    parquet_dir = Path(parquet_dir) if parquet_dir else PATHS.parquet
    cols = ["station_code", "site_timestamp", "rf1hr", "rf3hr", "rf6hr", "rf24hr"]
    r = pq.read_table(parquet_dir / "rain" / f"{year}.parquet", columns=cols).to_pandas()
    r["station_code"] = r["station_code"].astype(str)
    r["prefix"] = r["station_code"].str.split(".").str[1]

    g = (r.groupby(["prefix", "site_timestamp"], observed=True)
           .agg(rain_rf1hr_mean=("rf1hr", "mean"),
                rain_rf1hr_max=("rf1hr", "max"),      # the wettest gauge, not the average
                rain_rf3hr_mean=("rf3hr", "mean"),
                rain_rf3hr_max=("rf3hr", "max"),
                rain_rf6hr_mean=("rf6hr", "mean"),
                rain_rf24hr_mean=("rf24hr", "mean"),
                rain_gauges_reporting=("rf1hr", "count"))
           .reset_index()
           .sort_values(["prefix", "site_timestamp"]))

    grp = g.groupby("prefix", observed=True)
    # Is the rain intensifying or easing off? Intensification precedes flooding.
    g["rain_rf1hr_delta1h"] = grp["rain_rf1hr_mean"].diff(STEPS_1H)
    g["rain_rf1hr_delta3h"] = grp["rain_rf1hr_mean"].diff(3 * STEPS_1H)
    # Spread across gauges: high spread means a localised cell, which is
    # precisely when a district average understates the peak.
    g["rain_spread"] = g["rain_rf1hr_max"] - g["rain_rf1hr_mean"]
    # Antecedent wetness: ground already saturated drains far more slowly.
    g["rain_antecedent_ratio"] = g["rain_rf1hr_mean"] / (g["rain_rf24hr_mean"] + 1.0)
    return g


# ===========================================================================
# Water and flow features (citywide, until coordinates arrive)
# ===========================================================================

def water_city_features(year: int, parquet_dir: Path | None = None) -> pd.DataFrame:
    """Canal water-level indicators for the whole network, per timestamp.

    We use *changes*, not absolute levels, because the datum of `wl_in` has
    never been confirmed with BMA. A rise of 8 cm in an hour means the same
    thing whether the gauge reads from mean sea level or from the canal bed.
    """
    parquet_dir = Path(parquet_dir) if parquet_dir else PATHS.parquet
    w = pq.read_table(parquet_dir / "water" / f"{year}.parquet",
                      columns=["station_code", "site_timestamp", "wl_in"]).to_pandas()
    w["station_code"] = w["station_code"].astype(str)
    w = w.sort_values(["station_code", "site_timestamp"])
    grp = w.groupby("station_code", observed=True)["wl_in"]
    w["rise1h"] = grp.diff(STEPS_1H)
    w["rise3h"] = grp.diff(3 * STEPS_1H)

    return (w.groupby("site_timestamp")
              .agg(water_rise1h_mean=("rise1h", "mean"),
                   water_rise1h_max=("rise1h", "max"),
                   water_rise3h_mean=("rise3h", "mean"),
                   water_rising_share=("rise1h", lambda s: (s > 0.05).mean()),
                   water_offline_share=("wl_in", lambda s: s.isna().mean()))
              .reset_index())


def flow_city_features(year: int, parquet_dir: Path | None = None) -> pd.DataFrame:
    """Drainage-state indicators for the whole network, per timestamp.

    Stations marked `exclude_from_features` are dropped first. Right now that
    is only FW.PKG.01, the Chao Phraya river gauge, whose thousand-fold larger
    discharge would otherwise swamp every canal average.
    """
    parquet_dir = Path(parquet_dir) if parquet_dir else PATHS.parquet
    path = parquet_dir / "flow" / f"{year}.parquet"

    # Parquet written by an older version of the ingest has no
    # `exclude_from_features` column. Read what is actually there rather than
    # failing, and fall back to the station list in config — that way an
    # existing Parquet build stays usable and nobody has to re-run an hour of
    # ingestion to pick up one boolean.
    available = set(pq.ParquetFile(path).schema.names)
    wanted = ["station_code", "site_timestamp", "flow", "mean_velocity", "sensor_out"]
    if "exclude_from_features" in available:
        wanted.append("exclude_from_features")
    f = pq.read_table(path, columns=[c for c in wanted if c in available]).to_pandas()

    if "exclude_from_features" in f.columns:
        f = f.loc[~f["exclude_from_features"].fillna(False)]
    else:
        excluded = CFG["raw"]["datasets"]["flow"].get("exclude_from_features") or []
        if excluded:
            f = f.loc[~f["station_code"].astype(str).isin(excluded)]

    return (f.groupby("site_timestamp")
              .agg(flow_mean=("flow", "mean"),
                   flow_velocity_mean=("mean_velocity", "mean"),
                   # Negative flow means water is running backwards — a canal
                   # backing up, usually from tide or from a downstream block.
                   flow_negative_share=("flow", lambda s: (s < 0).mean()),
                   flow_offline_share=("sensor_out", "mean"))
              .reset_index())


# ===========================================================================
# Calendar and tide
# ===========================================================================

# Principal lunar semi-diurnal tide: 12.4206 hours. This governs the Chao
# Phraya's twice-daily rise and fall.
M2_PERIOD_HOURS = 12.4206
# Synodic month: the spring/neap cycle, which sets how big those tides get.
SPRING_NEAP_DAYS = 29.5306


def calendar_features(ts: pd.Series) -> pd.DataFrame:
    """Time-of-day, season and tidal phase, all as smooth cyclical values.

    Sin/cos pairs are used instead of raw hour numbers so that 23:55 and 00:05
    are neighbours rather than opposite ends of the range.

    The tide terms are a *proxy*, reconstructed from astronomy rather than
    measured. They give the model the phase of the tide, not its height. If BMA
    can supply Chao Phraya tide-gauge records, replace this with the real
    thing — the amplitude matters as much as the phase.
    """
    ts = pd.to_datetime(pd.Series(ts).reset_index(drop=True))
    hour = ts.dt.hour + ts.dt.minute / 60.0
    doy = ts.dt.dayofyear.astype(float)
    # Hours since a fixed epoch, used to advance the tidal phase.
    epoch_hours = (ts - pd.Timestamp("2019-01-01")).dt.total_seconds() / 3600.0

    out = pd.DataFrame({
        "cal_hour_sin": np.sin(2 * np.pi * hour / 24),
        "cal_hour_cos": np.cos(2 * np.pi * hour / 24),
        "cal_doy_sin": np.sin(2 * np.pi * doy / 365.25),
        "cal_doy_cos": np.cos(2 * np.pi * doy / 365.25),
        # Bangkok's rainy season, May to October.
        "cal_monsoon": ts.dt.month.isin([5, 6, 7, 8, 9, 10]).astype(np.int8),
        "tide_m2_sin": np.sin(2 * np.pi * epoch_hours / M2_PERIOD_HOURS),
        "tide_m2_cos": np.cos(2 * np.pi * epoch_hours / M2_PERIOD_HOURS),
        "tide_spring_neap": np.sin(2 * np.pi * epoch_hours / (SPRING_NEAP_DAYS * 24)),
    })
    return out


# ===========================================================================
# Optional joins — used only if the files have been generated
# ===========================================================================

def load_forecast_rain(path: Path | None = None) -> pd.DataFrame | None:
    """Weather-model rainfall per district and hour, if it has been fetched.

    Built by notebook 03b from the Open-Meteo historical-forecast archive.
    Returns None when the file is absent, and the pipeline carries on without
    it rather than failing.
    """
    path = Path(path) if path else PATHS.training / "forecast_rain.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)

    # The hourly timestamp column has been spelled differently by different
    # versions of notebook 03b — `hour_ts` in the 1.x builds, `site_hour` now.
    # Accept whichever is present rather than failing, so a forecast file
    # fetched once (an hour of API calls) stays usable across versions. Same
    # reasoning as the `exclude_from_features` fallback in flow_city_features.
    for candidate in ("site_hour", "site_timestamp", "hour_ts"):
        if candidate in df.columns:
            df["site_hour"] = pd.to_datetime(df[candidate]).dt.floor("h")
            break
    else:
        raise KeyError(
            f"{path.name} has no recognisable hourly timestamp column "
            f"(looked for site_hour, site_timestamp, hour_ts); got {list(df.columns)}")

    keep = ["prefix", "site_hour"] + [c for c in df.columns if c.startswith("rain_fcst")]
    return df[keep].drop_duplicates(["prefix", "site_hour"])


def load_station_spatial(path: Path | None = None) -> pd.DataFrame | None:
    """Per-station terrain attributes from the DEM, if they have been extracted."""
    path = Path(path) if path else PATHS.gis / "station_spatial.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    df["station_code"] = df["station_code"].astype(str)
    return df


# ===========================================================================
# The year builder — puts it all together
# ===========================================================================

def build_year(year: int,
               parquet_dir: Path | None = None,
               horizons: Iterable[int] | None = None,
               tiers: Iterable[float] | None = None,
               stride: int | None = None,
               verbose: bool = True) -> pd.DataFrame:
    """One year of flood stations -> one model-ready table.

    Each output row is (flood station, anchor timestamp) at the configured
    cadence, carrying its features and its future labels.
    """
    parquet_dir = Path(parquet_dir) if parquet_dir else PATHS.parquet
    horizons = list(horizons) if horizons is not None else list(CFG["forecast"]["horizons_h"])
    tiers = list(tiers) if tiers is not None else tier_values()
    stride = stride or anchor_stride()

    if verbose:
        print(f"[{year}] loading flood depths ...")
    fl = pq.read_table(parquet_dir / "flood" / f"{year}.parquet",
                       columns=["station_code", "site_timestamp", "flood"]).to_pandas()
    fl["station_code"] = fl["station_code"].astype(str)
    fl = fl.sort_values(["station_code", "site_timestamp"])

    if verbose:
        print(f"[{year}] building rain / water / flow aggregates ...")
    rain = rain_district_features(year, parquet_dir)
    water = water_city_features(year, parquet_dir)
    flow = flow_city_features(year, parquet_dir)

    frames = []
    for code, grp in fl.groupby("station_code", observed=True, sort=True):
        depth = grp["flood"].to_numpy(dtype=float)
        cols: dict[str, np.ndarray] = {}

        # ---- labels: strictly future, so the answer is never in the question
        for h in horizons:
            lab = future_window_labels(depth, h * STEPS_1H, tiers)
            cols[f"y_maxdepth_{h}h"] = lab["maxdepth"]
            cols[f"y_valid_{h}h"] = lab["valid"]
            for tier in tiers:
                cols[f"y_ge{int(tier)}_{h}h"] = lab[f"ge{int(tier)}"]

        # ---- features: only the past
        cols.update(flood_features(depth))

        sub = pd.DataFrame({"site_timestamp": grp["site_timestamp"].to_numpy(), **cols})
        sub = sub.iloc[::stride]                       # thin down to anchor rows
        sub.insert(0, "station_code", code)
        frames.append(sub)

    out = pd.concat(frames, ignore_index=True)
    out["prefix"] = out["station_code"].str.split(".").str[1]

    # ---- joins. Every source sits on the same 5-minute grid, so these are
    #      exact-key merges, not interpolations.
    out = out.merge(rain, on=["prefix", "site_timestamp"], how="left")
    out = out.merge(water, on="site_timestamp", how="left")
    out = out.merge(flow, on="site_timestamp", how="left")

    fcst = load_forecast_rain()
    if fcst is not None:
        out["site_hour"] = out["site_timestamp"].dt.floor("h")
        out = out.merge(fcst, on=["prefix", "site_hour"], how="left").drop(columns="site_hour")
    elif verbose:
        print(f"[{year}] no forecast_rain.parquet — skipping forecast-rain features")

    spatial = load_station_spatial()
    if spatial is not None:
        out = out.merge(spatial, on="station_code", how="left")
    elif verbose:
        print(f"[{year}] no station_spatial.parquet — skipping terrain features")

    # ---- calendar and tide
    out = pd.concat([out.reset_index(drop=True),
                     calendar_features(out["site_timestamp"])], axis=1)

    # ---- interaction: heavy rain on already-wet ground is the classic setup
    if {"rain_rf1hr_mean", "fl_max24h"} <= set(out.columns):
        out["rain_x_recent_flood"] = (out["rain_rf1hr_mean"].fillna(0)
                                      * out["fl_max24h"].fillna(0))

    # ---- onset flags, so evaluation can separate forecasting from monitoring
    for tier in tiers:
        out[f"is_onset_ge{int(tier)}"] = onset_mask(
            out["fl_depth_now"].to_numpy(dtype=float), tier).astype(np.int8)

    # Keep only anchors whose nearest-horizon label was at least partly observed.
    out = out[out[f"y_valid_{horizons[0]}h"] > 0].reset_index(drop=True)
    out["station_code"] = out["station_code"].astype("category")
    out["prefix"] = out["prefix"].astype("category")

    if verbose:
        primary = f"y_ge15_{horizons[0]}h"
        n_pos = int(out[primary].sum()) if primary in out else -1
        print(f"[{year}] {len(out):,} rows, {primary} positives: {n_pos:,}")
    return out


# ===========================================================================
# Feature list bookkeeping
# ===========================================================================

NON_FEATURE_PREFIXES = ("y_", "is_onset_")
NON_FEATURE_COLS = {"prefix", "site_timestamp", "site_hour"}


def feature_columns(df: pd.DataFrame, include_station: bool = True) -> list[str]:
    """Which columns the model is allowed to see.

    Labels, timestamps and the onset flags are excluded. The onset flag in
    particular must never become a feature: it is derived from the quantity the
    model is predicting, so including it would be a subtle leak.

    **`station_code` is included, as a categorical.** That deserves a word,
    because it is the feature that shapes the model's character:

    * It genuinely helps. Some sites flood twenty times a year and some never
      do, and knowing which is which is real, usable information.
    * It is also what makes the 6-hour forecast largely *climatological*. At
      long lead times the model leans on "this place floods often" because
      nothing else in the input tells it about a storm that has not arrived
      yet. It was the single largest input at 6 h in the previous version.

    Both facts are true at once. Keep the feature, and be honest in the report
    about what the long-horizon model is really doing. Pass
    `include_station=False` to train a station-agnostic model — useful for
    testing whether the model generalises to a site it has never seen, which is
    exactly the situation when BMA installs a new sensor.
    """
    drop = set(NON_FEATURE_COLS)
    if not include_station:
        drop.add("station_code")
    return [c for c in df.columns
            if not c.startswith(NON_FEATURE_PREFIXES) and c not in drop]


def label_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c.startswith("y_")]
