"""
Live feature assembly — from collected API data to model-ready rows.

--------------------------------------------------------------------------
WHAT THIS MODULE DOES
--------------------------------------------------------------------------
Takes live-collected data from `data/live/{thaiwater,openmeteo}/` and
transforms it into the same 50-feature contract the onset model was trained
on. The existing booster runs on these features identically — only the
source of the inputs differs.

--------------------------------------------------------------------------
THE HONEST SITUATION
--------------------------------------------------------------------------
With only the currently available public sources (ThaiWater canal + GFS
forecast rain + calendar + terrain), the model reaches **~5% event POD** —
it catches about 1 flood in 20. That is not a typo. The gap is BMA's 131
rain gauges, which have no public substitute.

Every feature from a source we don't have live is NaN. LightGBM handles
NaN natively — it was designed for exactly this — so the booster still
runs. It just has far less to work with.

Feature availability in live mode:

    fl_*            ALL NaN     no live road flood sensors
    rain_rf*        ALL NaN     no live BMA rain gauges
    rain_fcst_*     populated   Open-Meteo GFS (13 km grid)
    water_*         populated   ThaiWater canal levels (11 stations vs 300)
    flow_*          partial     ThaiWater flow_rate where available
    terr_*          populated   static from Phase 1 (on disk)
    cal_*, tide_*   populated   pure math from timestamp
    rain_x_*        NaN         interaction terms with NaN parents

This is feature set E from `live_forecasting_feasibility.md`, measured at
4.9% event POD. That number is a field in every live response, not a
footnote.

--------------------------------------------------------------------------
DO NOT IMPUTE MISSING SOURCES
--------------------------------------------------------------------------
NaN is correct. An invented rain gauge reading is worse than a missing one,
because the model cannot tell it was invented. LightGBM routes NaN to the
better child at each split — it has a learned policy for missing data that
is better than any constant we could guess.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .collectors.base import _repo_root, read_history, coverage, utc_now
from .config import load_config, resolve
from .features import (
    M2_HOURS, SYNODIC_DAYS,
    _FLOOD_COLS, _RAIN_COLS, _WF_COLS,
    calendar_features,
)
from .stations import load_registry, district_prefix


# -----------------------------------------------------------------------
# Performance measured on test year 2025, 15 cm / 1 h.
# These ride along with every live response.
# -----------------------------------------------------------------------
LIVE_MODE = "live_public"

LIVE_PERFORMANCE = {
    "event_pod": 0.049,
    "precision": 0.02,
    "measured_on": "test year 2025, 15 cm / 1 h, feature set E "
                   "(canal + GFS + calendar + terrain, no BMA rain/flood)",
    "plain_english": "Catches about 1 flood in 20. Not suitable for dispatch.",
    "compared_to_replay": {
        "replay_event_pod": 0.533,
        "explanation": "Replay uses all 50 features from 7 years of BMA data. "
                       "Live mode is missing road flood sensors and rain gauges "
                       "— the two most valuable inputs.",
    },
}


def _live_caveats() -> List[str]:
    """Caveats specific to live mode. Every one is earned by measurement."""
    return [
        "LIVE MODE on partial public data — catches about 1 flood in 20.",
        "Road flood sensors (fl_*) are unavailable: all NaN.",
        "BMA rain gauges (rain_rf*) are unavailable: all NaN.",
        "Canal data from ThaiWater: 11 stations vs 300 in training.",
        "GFS forecast rain is 13 km grid vs 2–5 km storm cells.",
        "Roughly 84% of alerts at this threshold do not become floods.",
        "Station coordinates are district centroids.",
        "Predicted depth is not served.",
    ]


# -----------------------------------------------------------------------
# Cold start
# -----------------------------------------------------------------------
def cold_start_check() -> Dict[str, Any]:
    """Has enough data been collected to make live predictions meaningful?

    Features like `fl_max_24h` and `rain_rf24hr_mean` look back 24 hours.
    Until every source has at least 24h of continuous collection, the system
    should flag cold_start=True. A confident zero from a system with no
    history is the worst possible output.
    """
    sources = ("thaiwater", "openmeteo")
    reports = {s: coverage(s) for s in sources}
    any_cold = any(r["cold_start"] for r in reports.values())

    return {
        "cold_start": any_cold,
        "sources": reports,
        "minimum_hours": 24,
        "note": ("System needs at least 24h of continuous collection before "
                 "predictions are meaningful." if any_cold
                 else "Collection history sufficient."),
    }


# -----------------------------------------------------------------------
# Live water/flow features from ThaiWater
# -----------------------------------------------------------------------
def live_water_features(lookback_hours: int = 6) -> Dict[str, float]:
    """Aggregate ThaiWater canal readings into the model's water/flow features.

    Returns a dict with the same keys as `_WF_COLS`. These are CITYWIDE
    aggregates — exactly what the model was trained on, since canal codes
    name canals, not districts.

    ThaiWater gives us `waterlevel_msl`, `waterlevel_msl_previous`, `wl_rise_m`,
    `flow_rate`, and `discharge`. We compute:
      - water_rise_1h_mean/max: from wl_rise_m (single-step rise)
      - water_rise_3h_mean: approximated from available data
      - water_rising_share: fraction of stations with positive rise
      - water_offline_share: fraction with NaN readings
      - flow_mean, flow_velocity_mean: from flow_rate / discharge
      - flow_negative_share, flow_offline_share
    """
    df = read_history("thaiwater")
    if df.empty:
        return {c: np.nan for c in _WF_COLS}

    # Use only recent readings
    df["_fetched_at_utc"] = pd.to_datetime(df["_fetched_at_utc"])
    cutoff = pd.Timestamp(utc_now()).tz_localize(None) - pd.Timedelta(hours=lookback_hours)
    recent = df[df["_fetched_at_utc"] >= cutoff]

    if recent.empty:
        return {c: np.nan for c in _WF_COLS}

    # Take the most recent poll only for current snapshot
    latest_poll = recent["_fetched_at_utc"].max()
    snap = recent[recent["_fetched_at_utc"] == latest_poll].copy()

    # Water rise features
    rise = pd.to_numeric(snap.get("wl_rise_m", pd.Series(dtype=float)), errors="coerce")
    wl = pd.to_numeric(snap.get("waterlevel_msl", pd.Series(dtype=float)), errors="coerce")

    n_total = len(snap)
    n_wl_valid = wl.notna().sum()

    result = {
        "water_rise_1h_mean": float(rise.mean()) if rise.notna().any() else np.nan,
        "water_rise_1h_max": float(rise.max()) if rise.notna().any() else np.nan,
        # ThaiWater is hourly, not 5-min, so 3h rise is approximated from
        # available history. Use NaN if we don't have enough history.
        "water_rise_3h_mean": np.nan,
        "water_rising_share": (
            float((rise > 0).sum() / rise.notna().sum())
            if rise.notna().any() else np.nan
        ),
        "water_offline_share": (
            float(1.0 - n_wl_valid / n_total) if n_total > 0 else np.nan
        ),
        "flow_mean": np.nan,
        "flow_velocity_mean": np.nan,
        "flow_negative_share": np.nan,
        "flow_offline_share": np.nan,
    }

    # Flow features from ThaiWater (if available)
    flow = pd.to_numeric(snap.get("flow_rate", pd.Series(dtype=float)), errors="coerce")
    discharge = pd.to_numeric(snap.get("discharge", pd.Series(dtype=float)), errors="coerce")

    flow_valid = flow.notna() | discharge.notna()
    flow_values = flow.fillna(discharge)

    if flow_valid.any():
        result["flow_mean"] = float(flow_values.mean())
        result["flow_negative_share"] = (
            float((flow_values < 0).sum() / flow_valid.sum())
            if flow_valid.sum() > 0 else np.nan
        )
        result["flow_offline_share"] = float(1.0 - flow_valid.sum() / n_total)

    # Try to compute 3h rise from history if we have enough polls
    if len(recent) > len(snap):
        polls = recent.groupby("_fetched_at_utc")["waterlevel_msl"].mean()
        polls = polls.dropna().sort_index()
        if len(polls) >= 2:
            three_h_ago = latest_poll - pd.Timedelta(hours=3)
            old = polls[polls.index <= three_h_ago]
            if not old.empty:
                result["water_rise_3h_mean"] = float(polls.iloc[-1] - old.iloc[-1])

    return result


# -----------------------------------------------------------------------
# Live forecast rain from Open-Meteo GFS
# -----------------------------------------------------------------------
def live_rain_forecast() -> Dict[str, float]:
    """Extract GFS forecast rain per district from collected Open-Meteo data.

    Returns a dict with keys `rain_fcst_1h`, `rain_fcst_3h`, `rain_fcst_6h`
    — the cumulative forecast rainfall over each horizon.

    GFS is a 13 km grid. Bangkok floods from convective cells 2–5 km across.
    Measured on its own this reaches 1.6% event POD. It is a weak prior,
    not a forecast system.
    """
    df = read_history("openmeteo")
    if df.empty:
        return {"rain_fcst_1h": np.nan, "rain_fcst_3h": np.nan, "rain_fcst_6h": np.nan}

    df["_fetched_at_utc"] = pd.to_datetime(df["_fetched_at_utc"])
    latest_poll = df["_fetched_at_utc"].max()
    snap = df[df["_fetched_at_utc"] == latest_poll].copy()

    if snap.empty or "is_forecast" not in snap.columns:
        return {"rain_fcst_1h": np.nan, "rain_fcst_3h": np.nan, "rain_fcst_6h": np.nan}

    # Only use actual forecast rows (not the model's recent analysis)
    fwd = snap[snap["is_forecast"] == True].copy()  # noqa: E712
    if fwd.empty:
        return {"rain_fcst_1h": np.nan, "rain_fcst_3h": np.nan, "rain_fcst_6h": np.nan}

    precip = pd.to_numeric(fwd.get("precip_mm", pd.Series(dtype=float)), errors="coerce")
    lead = pd.to_numeric(fwd.get("lead_hours", pd.Series(dtype=float)), errors="coerce")

    result = {}
    for h in (1, 3, 6):
        mask = lead.between(0, h, inclusive="right")
        vals = precip[mask]
        # Mean across districts, sum across hours in the window
        if vals.notna().any():
            by_district = fwd.loc[mask].groupby("district")["precip_mm"].sum()
            result[f"rain_fcst_{h}h"] = float(by_district.mean())
        else:
            result[f"rain_fcst_{h}h"] = np.nan

    return result


# -----------------------------------------------------------------------
# Terrain (static, on disk)
# -----------------------------------------------------------------------
@lru_cache(maxsize=1)
def _terrain_by_district() -> Dict[str, Dict[str, float]]:
    """Load the district terrain table from Phase 1."""
    path = resolve("data/features/terrain_district_ground.parquet")
    if not path.exists():
        return {}
    terr = pd.read_parquet(path)
    want = {
        "elev_m_p50": "terr_elev_m_p50",
        "elev_m_p10": "terr_elev_m_p10",
        "depression_depth_m_p95": "terr_depression_depth_m_p95",
        "depressed_area_share": "terr_depressed_area_share",
        "slope_deg_p50": "terr_slope_deg_p50",
    }
    out = {}
    for _, row in terr.iterrows():
        d = str(row.get("district", ""))
        if not d:
            continue
        out[d] = {want[k]: float(row[k]) for k in want if k in row.index and pd.notna(row[k])}
    return out


_TERRAIN_FEATURES = [
    "terr_elev_m_p50", "terr_elev_m_p10", "terr_depression_depth_m_p95",
    "terr_depressed_area_share", "terr_slope_deg_p50",
]


# -----------------------------------------------------------------------
# Station list
# -----------------------------------------------------------------------
@lru_cache(maxsize=1)
def _flood_stations() -> pd.DataFrame:
    """The 107 flood stations the model knows about, with their districts."""
    reg = load_registry()
    flood = reg[reg["sensor_type"].str.lower().str.startswith("fl", na=False)].copy()
    flood["district_code"] = flood["station_code"].map(district_prefix)
    return flood[["station_code", "district_code", "district"]].drop_duplicates("station_code")


@lru_cache(maxsize=1)
def _district_code_to_name() -> Dict[str, str]:
    """district code prefix -> district name."""
    reg = load_registry()
    reg = reg.dropna(subset=["district"])
    reg["code"] = reg["station_code"].map(district_prefix)
    cfg = load_config()
    alias = cfg.get("terrain", {}).get("district_name_aliases", {})
    reg["district"] = reg["district"].map(lambda d: alias.get(d, d))
    return reg.drop_duplicates("code").set_index("code")["district"].to_dict()


# -----------------------------------------------------------------------
# Calendar and tide — pure math from timestamp
# -----------------------------------------------------------------------
def _calendar_dict(ts: pd.Timestamp) -> Dict[str, float]:
    """Compute calendar and tide features for a single timestamp."""
    hour = ts.hour + ts.minute / 60.0
    doy = ts.day_of_year
    since_h = (ts - pd.Timestamp("2019-01-01")).total_seconds() / 3600.0

    return {
        "cal_hour_sin": float(np.sin(2 * np.pi * hour / 24)),
        "cal_hour_cos": float(np.cos(2 * np.pi * hour / 24)),
        "cal_doy_sin": float(np.sin(2 * np.pi * doy / 365.25)),
        "cal_doy_cos": float(np.cos(2 * np.pi * doy / 365.25)),
        "cal_monsoon": 1.0 if 5 <= ts.month <= 10 else 0.0,
        "tide_m2_sin": float(np.sin(2 * np.pi * since_h / M2_HOURS)),
        "tide_m2_cos": float(np.cos(2 * np.pi * since_h / M2_HOURS)),
        "tide_spring_neap": float(np.cos(2 * np.pi * since_h / (SYNODIC_DAYS * 24))),
    }


# -----------------------------------------------------------------------
# The main assembly
# -----------------------------------------------------------------------
def live_features(ts: Optional[pd.Timestamp] = None) -> pd.DataFrame:
    """Build the model's 50-feature row for every station, from live data.

    Returns a DataFrame with one row per flood station and columns matching
    the onset model's feature contract exactly. Features from unavailable
    sources are NaN — which is correct, not a bug.

    Parameters
    ----------
    ts : optional timestamp; defaults to the most recent collector poll time.
    """
    # Resolve timestamp
    if ts is None:
        status_path = _repo_root() / "data" / "live" / "_status.json"
        if status_path.exists():
            status = json.loads(status_path.read_text())
            sources = status.get("sources", [])
            times = []
            for s in sources:
                if s.get("ok") and s.get("fetched_at_utc"):
                    times.append(pd.Timestamp(s["fetched_at_utc"]))
            if times:
                ts = max(times)
        if ts is None:
            ts = pd.Timestamp(utc_now()).tz_localize(None)

    # Snap to 15-minute grid
    step = load_config()["data"]["model_cadence_minutes"]
    ts = ts.floor(f"{step}min")

    # Get station list
    stations = _flood_stations()
    code_to_name = _district_code_to_name()

    # Collect live inputs
    water_feats = live_water_features()
    rain_fcst = live_rain_forecast()
    cal = _calendar_dict(ts)
    terrain = _terrain_by_district()

    # Build one row per station
    rows = []
    for _, st in stations.iterrows():
        row = {
            "station_code": st["station_code"],
            "district": st.get("district") or code_to_name.get(st["district_code"]),
            "ts": ts,
        }

        # Flood autoregressive: ALL NaN — no live road flood sensors
        for c in _FLOOD_COLS:
            row[c] = np.nan

        # Rain gauge features: ALL NaN — no live BMA rain gauges
        for c in _RAIN_COLS:
            row[c] = np.nan

        # Water/flow features: from ThaiWater (citywide)
        row.update(water_feats)

        # GFS forecast rain
        row.update(rain_fcst)

        # Terrain: static, by district
        district_name = row["district"]
        terr = terrain.get(district_name, {})
        for c in _TERRAIN_FEATURES:
            row[c] = terr.get(c, np.nan)

        # Calendar and tide
        row.update(cal)

        # Interaction terms — NaN when either parent is NaN
        rain_1h = row.get("rain_rf1hr_mean", np.nan)
        fl_max_24h = row.get("fl_max_24h", np.nan)
        depression = row.get("terr_depression_depth_m_p95", np.nan)

        row["rain_x_recent_flood"] = (
            rain_1h * fl_max_24h
            if pd.notna(rain_1h) and pd.notna(fl_max_24h)
            else np.nan
        )
        row["rain_x_depression"] = (
            rain_1h * depression
            if pd.notna(rain_1h) and pd.notna(depression)
            else np.nan
        )

        rows.append(row)

    df = pd.DataFrame(rows)

    # Cast all feature columns to float32, matching the training pipeline
    feature_cols = [c for c in df.columns if c not in ("station_code", "district", "ts")]
    for c in feature_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float32")

    return df


def live_status() -> Dict[str, Any]:
    """Full status report for the live collection system."""
    status_path = _repo_root() / "data" / "live" / "_status.json"
    collector_status = {}
    if status_path.exists():
        collector_status = json.loads(status_path.read_text())

    cold = cold_start_check()

    return {
        "data_mode": LIVE_MODE,
        "cold_start": cold["cold_start"],
        "cold_start_detail": cold,
        "collector": collector_status,
        "mode_performance": LIVE_PERFORMANCE,
        "available_sources": ["thaiwater", "openmeteo", "traffy"],
        "missing_sources": [
            "bma_rain_gauges (131 stations, 5-min — the biggest gap)",
            "bma_road_flood_sensors (107 stations — the target variable)",
            "bma_canal_full_network (300 stations vs ThaiWater's 11)",
        ],
        "features_populated": [
            "water_rise_1h_mean/max (ThaiWater, 11 stations)",
            "water_rising_share, water_offline_share",
            "rain_fcst_1h/3h/6h (GFS 13 km grid)",
            "terr_* (static, from Phase 1 DTM)",
            "cal_*, tide_* (computed from timestamp)",
        ],
        "features_nan": [
            "fl_* (all 12 flood-sensor features)",
            "rain_rf* (all 11 rain-gauge features)",
            "flow_velocity_mean (no source)",
            "rain_x_* (interaction terms with NaN parents)",
        ],
    }
