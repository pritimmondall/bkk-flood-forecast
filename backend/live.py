#!/usr/bin/env python3
"""Live feature builder: Open-Meteo rain -> model feature rows.

Turns the replay-only API into a live one. What's real vs missing:

  REAL (from Open-Meteo, refreshed every 10 min):
    rain_rf1hr_mean/max, rain_rf3hr_mean, rain_rf24hr_mean,
    rain_rf1hr_delta1h, calendar features
  MISSING (no live BMA sensor feed yet -> NaN, the same pattern the model
  saw during sensor outages in training):
    fl_* (station flood-depth history), water_*, flow_*

Consequence: live predictions are rain + climatology driven — genuinely
useful for "is this district heading into trouble", but weaker than replay
mode at 1h (where flood-depth history is the top feature) and persistence
alerts (depth_now) cannot fire. This is the documented degraded mode; the
BMA sensor feed drops into `build_live_rows` later without touching the API
contract.

District rain locations come from `backend/district_centroids.csv`
(prefix,lat,lon). It ships with every prefix defaulting to central Bangkok —
one shared rain point for the whole city. The Data/GIS engineer should fill
in real district centroids; per-district rain then works automatically.

Open-Meteo: https://open-meteo.com — free, no API key, hourly precipitation,
past_days gives the trailing accumulations.
"""

from __future__ import annotations

import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

BKK_CENTER = (13.7563, 100.5018)
CACHE_TTL_S = 600
_cache: dict = {}


# ---------------------------------------------------------------------------
# District centroids
# ---------------------------------------------------------------------------

def load_centroids(prefixes: list[str]) -> dict[str, tuple[float, float]]:
    """prefix -> (lat, lon). Missing file/rows fall back to central Bangkok."""
    path = Path(__file__).parent / "district_centroids.csv"
    table = {}
    if path.exists():
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    table[row["prefix"]] = (float(row["lat"]),
                                            float(row["lon"]))
                except (KeyError, ValueError):
                    continue
    return {p: table.get(p, BKK_CENTER) for p in prefixes}


def write_default_centroids(prefixes: list[str]) -> None:
    """Create the template CSV (all rows = Bangkok center) if absent."""
    path = Path(__file__).parent / "district_centroids.csv"
    if path.exists():
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["prefix", "lat", "lon"])
        for p in sorted(prefixes):
            w.writerow([p, BKK_CENTER[0], BKK_CENTER[1]])


# ---------------------------------------------------------------------------
# Open-Meteo
# ---------------------------------------------------------------------------

def _fetch_hourly_precip(lat: float, lon: float) -> tuple[list[str], list[float]]:
    key = (round(lat, 3), round(lon, 3))
    now = time.time()
    if key in _cache and now - _cache[key][0] < CACHE_TTL_S:
        return _cache[key][1]
    params = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "hourly": "precipitation",
        "past_days": 2, "forecast_days": 1,
        "timezone": "Asia/Bangkok",
    })
    url = f"https://api.open-meteo.com/v1/forecast?{params}"
    with urllib.request.urlopen(url, timeout=15) as r:
        data = json.loads(r.read())
    result = (data["hourly"]["time"], data["hourly"]["precipitation"])
    _cache[key] = (now, result)
    return result


def rain_features_at(lat: float, lon: float,
                     now: pd.Timestamp) -> dict[str, float]:
    """Trailing rain accumulations (mm) ending at the current hour."""
    times, precip = _fetch_hourly_precip(lat, lon)
    ts = pd.to_datetime(times)
    precip = np.array([p if p is not None else np.nan for p in precip],
                      dtype=float)
    # index of the current (started) hour
    idx = int(np.searchsorted(ts, now.floor("h"), side="right")) - 1
    if idx < 0:
        raise RuntimeError("Open-Meteo window does not cover 'now'")

    def back(n):                       # sum of the trailing n full hours
        return float(np.nansum(precip[max(0, idx - n + 1): idx + 1]))

    rf1 = back(1)
    prev1 = float(np.nansum(precip[max(0, idx - 1): idx])) if idx >= 1 else 0.0
    return {
        "rain_rf1hr_mean": rf1,
        "rain_rf1hr_max": rf1,          # single point per district for now
        "rain_rf3hr_mean": back(3),
        "rain_rf24hr_mean": back(24),
        "rain_rf1hr_delta1h": rf1 - prev1,
    }


# ---------------------------------------------------------------------------
# Feature rows
# ---------------------------------------------------------------------------

def build_live_rows(stations: list[str], feature_names: list[str],
                    now: pd.Timestamp | None = None) -> pd.DataFrame:
    """One feature row per station, matching the training feature contract."""
    now = now or pd.Timestamp.now(tz="Asia/Bangkok").tz_localize(None)
    prefixes = sorted({s.split(".")[1] for s in stations})
    centroids = load_centroids(prefixes)

    # one API call per unique coordinate (all-default file -> single call)
    rain_by_prefix = {}
    for p in prefixes:
        rain_by_prefix[p] = rain_features_at(*centroids[p], now)

    hour = now.hour + now.minute / 60.0
    doy = float(now.dayofyear)
    cal = {
        "cal_hour_sin": np.sin(2 * np.pi * hour / 24),
        "cal_hour_cos": np.cos(2 * np.pi * hour / 24),
        "cal_doy_sin": np.sin(2 * np.pi * doy / 365.25),
        "cal_doy_cos": np.cos(2 * np.pi * doy / 365.25),
        "cal_monsoon": 1 if now.month in (5, 6, 7, 8, 9, 10) else 0,
    }

    rows = []
    for code in stations:
        row = {name: np.nan for name in feature_names}   # sensors: missing
        row.update(rain_by_prefix[code.split(".")[1]])
        row.update(cal)
        row["station_code"] = code
        row["site_timestamp"] = now
        rows.append(row)
    df = pd.DataFrame(rows)
    df["station_code"] = df["station_code"].astype("category")
    return df
