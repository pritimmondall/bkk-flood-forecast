"""
Open-Meteo — forecast and recent rainfall at district centroids.

--------------------------------------------------------------------------
READ THIS BEFORE TRUSTING ANYTHING THIS COLLECTOR RETURNS
--------------------------------------------------------------------------
GFS is a **13 km grid**. Bangkok floods from convective cells two to five
kilometres across. Measured on its own (feature set B: GFS + calendar + terrain)
this reaches **1.6% event POD at 0.2% precision** against replay's 53%.

That is not a forecast system. It is a weak prior.

It is collected because the model's `rain_fcst_1h/3h/6h` features expect it, and
because it is the only rainfall input available with nobody's permission. It must
never be presented as a substitute for the BMA gauge network, and a dashboard
running on this alone should not be shown to anyone who might act on it.

--------------------------------------------------------------------------
FORECAST, NOT REANALYSIS
--------------------------------------------------------------------------
`external.py` already contains `assert_forecast_is_not_reanalysis` for a reason:
the archive endpoint and the forecast endpoint have overlapping shapes, and
silently training on reanalysis would leak the future into the features. This
collector only ever calls the FORECAST endpoint, and records
`is_forecast=True/False` per row so the distinction survives into the parquet.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .base import http_get_json, utc_now

ENDPOINT = "https://api.open-meteo.com/v1/forecast"

#: Bangkok bounding box, sampled on a coarse grid when no district centroid
#: table is available. Deliberately small: 13 km cells mean extra points buy
#: almost nothing but do multiply the request count.
FALLBACK_POINTS: List[Dict[str, Any]] = [
    {"district": "grid_nw", "lat": 13.85, "long": 100.42},
    {"district": "grid_ne", "lat": 13.85, "long": 100.68},
    {"district": "grid_c",  "lat": 13.75, "long": 100.53},
    {"district": "grid_sw", "lat": 13.65, "long": 100.42},
    {"district": "grid_se", "lat": 13.68, "long": 100.68},
]

HOURLY_VARS = "precipitation,rain,precipitation_probability"


def _district_points() -> pd.DataFrame:
    """Prefer the project's own district centroids; fall back to a coarse grid.

    `external.district_points()` builds these from the admin boundary layer. If
    that import fails (running outside the repo, or the boundary file is not
    materialised) we still want the collector to work rather than refuse.
    """
    try:
        from ..external import district_points  # type: ignore

        df = district_points()
        cols = {c.lower(): c for c in df.columns}
        lat = cols.get("lat") or cols.get("latitude")
        lon = cols.get("long") or cols.get("lon") or cols.get("longitude")
        dis = cols.get("district") or cols.get("district_en") or list(df.columns)[0]
        if lat and lon:
            return df.rename(columns={lat: "lat", lon: "long", dis: "district"})[
                ["district", "lat", "long"]
            ]
    except Exception:  # noqa: BLE001 - fallback is the point
        pass
    return pd.DataFrame(FALLBACK_POINTS)


def parse(payload: Any, district: str, lat: float, lon: float) -> pd.DataFrame:
    """One point's hourly series -> tidy rows."""
    hourly = (payload or {}).get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        return pd.DataFrame()

    df = pd.DataFrame(
        {
            "ts": pd.to_datetime(times, errors="coerce"),
            "precip_mm": pd.to_numeric(hourly.get("precipitation", []), errors="coerce"),
            "rain_mm": pd.to_numeric(hourly.get("rain", []), errors="coerce"),
            "precip_prob": pd.to_numeric(
                hourly.get("precipitation_probability", []), errors="coerce"
            ),
        }
    )
    df["district"] = district
    df["lat"] = lat
    df["long"] = lon
    df["model"] = (payload or {}).get("model", "gfs_seamless")
    df["grid_km"] = 13.0

    # Anything at or after the request time is a forecast; anything before it is
    # the model's own recent analysis. Both are useful and they are not the same
    # thing, so the row says which it is.
    now = pd.Timestamp(utc_now()).tz_localize(None)
    df["is_forecast"] = df["ts"] >= now
    df["lead_hours"] = ((df["ts"] - now).dt.total_seconds() / 3600.0).round(2)
    return df


def fetch(points: Optional[pd.DataFrame] = None,
          past_days: int = 2,
          forecast_days: int = 2) -> Tuple[pd.DataFrame, Any]:
    pts = points if points is not None else _district_points()
    frames: List[pd.DataFrame] = []
    raw: Dict[str, Any] = {}

    for r in pts.itertuples():
        payload = http_get_json(
            ENDPOINT,
            params={
                "latitude": float(r.lat),
                "longitude": float(r.long),
                "hourly": HOURLY_VARS,
                "past_days": past_days,
                "forecast_days": forecast_days,
                "timezone": "UTC",
                "models": "gfs_seamless",
            },
        )
        raw[str(r.district)] = payload
        frames.append(parse(payload, str(r.district), float(r.lat), float(r.long)))

    if not frames:
        return pd.DataFrame(), raw
    return pd.concat(frames, ignore_index=True), raw


SPEC = {
    "name": "openmeteo",
    "fetch": fetch,
    "time_col": "ts",
    "cadence_minutes": 60,
    "needs_permission": False,
    "provides": ["forecast rain 1h/3h/6h (13 km grid)", "recent modelled rain"],
    "verified": "already in use via external.py; measured at 1.6% event POD alone",
}
