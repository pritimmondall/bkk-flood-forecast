"""
Serving the forecast. Phase 7 — the importable core.

The FastAPI app in `backend/` is a thin shell over this module. Everything that
can be tested without a web server lives here.

--------------------------------------------------------------------------
THIS SERVES REPLAY, NOT LIVE DATA
--------------------------------------------------------------------------
There is no live feed. BMA's sensors are not exposed to us as an API, and
`pumps.bangkok.go.th` was deliberately not scraped (project rule 8). So the
service reads the historical feature tables and answers "what would the system
have said at time T".

That is genuinely useful — it is how the dashboard gets built and demonstrated —
and it is dangerous the moment somebody forgets. So **every response carries
`data_mode: "replay"` and the timestamp it is replaying**. Not a footnote in a
document, a field in the JSON. A caveat that lives only in a PDF may as well not
exist (project rule 6).

--------------------------------------------------------------------------
WHAT THE API MUST NEVER IMPLY
--------------------------------------------------------------------------
Measured in Phases 4 and 5, and reproduced in `model_card()`:

  * about 84% of alerts are false at the operating threshold
  * three quarters of detections come with a single 15-minute step of warning
  * the system generates ~6.6 separate call-outs per flood it warns about
  * station coordinates are DISTRICT CENTROIDS — every sensor in a district
    plots at the same point. A map that draws them as precise pins is lying.
  * predicted depth is not published at all: the intervals failed their
    coverage check (43-63% against a 90% target)

Each of those is a field, not prose.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from .config import load_config, resolve
from .rawio import connect

DATA_MODE_REPLAY = "replay"
DATA_MODE_LIVE = "live_public"


def _data_mode(mode: str) -> str:
    return DATA_MODE_LIVE if mode == "live" else DATA_MODE_REPLAY


def _json_safe(obj):
    """Replace NaN and infinity with None, recursively.

    JSON has no NaN. A district where every sensor is offline produces
    `max(depth) = NaN`, which serialises to the literal token `NaN` — invalid
    JSON that `json.loads` in a browser rejects outright. The whole response
    fails, so one dead district takes down the map rather than showing a gap.

    Caught by `test_district_risk_denies_being_a_flood_extent`, which was
    written to check the wording of a note and found this instead.
    """
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (float, np.floating)):
        return None if not np.isfinite(obj) else float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    return obj


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------
class ModelBundle:
    """A trained booster plus everything needed to use it correctly.

    The metadata is not bookkeeping. Without `negative_rate` the probabilities
    cannot be corrected and the model is unservable; without `features` the
    column order is a guess; without `threshold` there is no alert rule. They
    travel together or not at all.
    """

    def __init__(self, name: str):
        import lightgbm as lgb

        d = resolve("models")
        self.name = name
        self.meta = json.loads((d / f"{name}.json").read_text())
        self.booster = lgb.Booster(model_file=str(d / f"{name}.txt"))
        self.features: List[str] = self.meta["features"]
        self.threshold: float = self.meta["threshold"]
        self.negative_rate: float = self.meta["negative_rate"]
        self.tier_cm: int = self.meta["tier_cm"]
        self.horizon_h: int = self.meta["horizon_h"]
        self.kind: str = self.meta["kind"]

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        from .models import correct_for_downsampling

        raw = self.booster.predict(X[self.features])
        return correct_for_downsampling(raw, self.negative_rate)

    def raw_score(self, X: pd.DataFrame) -> np.ndarray:
        """Uncorrected score — the quantity the threshold was chosen against.

        The threshold came from `best_threshold` on downsampled validation data,
        so it must be compared against the same scale. Comparing it to the
        corrected probability would silently shift the operating point by a
        factor of four.
        """
        return self.booster.predict(X[self.features])


@lru_cache(maxsize=8)
def load_bundle(name: str = "onset_t15_h1_final") -> ModelBundle:
    return ModelBundle(name)


# ---------------------------------------------------------------------------
# Replay clock
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def available_range() -> Dict[str, str]:
    """First and last timestamp the service can answer for."""
    con = connect()
    try:
        paths = _feature_paths()
        lo, hi = con.execute(
            f"SELECT min(ts), max(ts) FROM read_parquet({paths})").fetchone()
    finally:
        con.close()
    return {"first": str(lo), "last": str(hi)}


def _feature_paths() -> List[str]:
    cfg = load_config()["data"]["years"]
    years = range(cfg[0], cfg[-1] + 1) if len(cfg) == 2 else cfg
    return [str(resolve(f"data/features/features_{y}.parquet"))
            for y in years
            if resolve(f"data/features/features_{y}.parquet").exists()]


def resolve_timestamp(ts: Optional[str] = None) -> pd.Timestamp:
    """Snap a requested time to the modelling grid, or take the latest.

    Requests that fall between 15-minute stamps are floored rather than
    rejected. A dashboard polling on a wall clock will almost never land exactly
    on the grid, and refusing it would make the service unusable for the thing
    it exists to serve.
    """
    step = load_config()["data"]["model_cadence_minutes"]
    if ts is None:
        return pd.Timestamp(available_range()["last"])
    t = pd.Timestamp(ts)
    return t.floor(f"{step}min")


# ---------------------------------------------------------------------------
# The forecast
# ---------------------------------------------------------------------------
def forecast_at(ts: Optional[str] = None, bundle_name: str = "onset_t15_h1_final",
                con=None, mode: str = "replay") -> Dict[str, object]:
    """Every station's risk at one moment, with the caveats attached.

    An ONSET model is being served, so it is only entitled to speak about roads
    that are currently below the tier. Stations already at or above it are
    returned with `status: "flooded_now"` and no prediction — the honest answer,
    rather than a number from a model that never saw such rows in training.

    In live mode, features come from `live.live_features()` instead of the
    historical parquet. The model and threshold are unchanged — only the source
    of inputs differs. Measured at ~5% event POD.
    """
    b = load_bundle(bundle_name)
    data_mode = _data_mode(mode)

    if mode == "live":
        return _forecast_live(b, bundle_name, ts)

    # --- Replay mode (existing behavior) ---
    t = resolve_timestamp(ts)
    onset_col = f"is_onset_{b.tier_cm}_{b.horizon_h}h"

    owns = con is None
    con = con or connect()
    try:
        paths = _feature_paths()
        cols = ", ".join(f'"{ c}"' for c in b.features)
        df = con.execute(f"""
            SELECT station_code, district, fl_depth_now, {onset_col} AS is_onset,
                   {cols}
            FROM read_parquet({paths}) WHERE ts = TIMESTAMP '{t}'
        """).fetchdf()
    finally:
        if owns:
            con.close()

    if df.empty:
        return {"timestamp": str(t), "data_mode": DATA_MODE_REPLAY, "stations": [],
                "error": "no data at this timestamp",
                "available": available_range()}

    dry = df["is_onset"].fillna(False).to_numpy(dtype=bool)
    prob = np.full(len(df), np.nan)
    raw = np.full(len(df), np.nan)
    if dry.any():
        prob[dry] = b.predict(df.loc[dry])
        raw[dry] = b.raw_score(df.loc[dry])

    out = []
    for i, r in enumerate(df.itertuples()):
        depth = None if pd.isna(r.fl_depth_now) else float(r.fl_depth_now)
        if depth is None:
            status, alert = "sensor_offline", False
        elif not dry[i]:
            status, alert = "flooded_now", True
        else:
            alert = bool(raw[i] >= b.threshold)
            status = "at_risk" if alert else "clear"
        out.append({
            "station_code": r.station_code,
            "district": r.district,
            "depth_now_cm": depth,
            "status": status,
            "alert": alert,
            "probability": None if np.isnan(prob[i]) else round(float(prob[i]), 5),
            # Deliberately absent: predicted depth. See `model_card`.
            "predicted_depth_cm": None,
        })

    n_alert = sum(o["alert"] for o in out)
    out = _json_safe(out)
    return {
        "timestamp": str(t),
        "data_mode": DATA_MODE_REPLAY,
        "replay_note": "Historical replay. This is what the system would have "
                       "said at this timestamp; it is not a live feed.",
        "tier_cm": b.tier_cm,
        "horizon_hours": b.horizon_h,
        "model": bundle_name,
        "stations": out,
        "counts": {
            "total": len(out),
            "alerting": int(n_alert),
            "flooded_now": sum(o["status"] == "flooded_now" for o in out),
            "sensor_offline": sum(o["status"] == "sensor_offline" for o in out),
        },
        "caveats": response_caveats(),
    }


def _forecast_live(b, bundle_name: str,
                   ts: Optional[str] = None) -> Dict[str, object]:
    """Live forecast: build features from collected API data and run the model."""
    from .live import (
        LIVE_MODE, LIVE_PERFORMANCE, _live_caveats,
        cold_start_check, live_features,
    )

    t = pd.Timestamp(ts) if ts else None
    df = live_features(t)

    if df.empty:
        return {
            "timestamp": str(t or pd.Timestamp.now()),
            "data_mode": LIVE_MODE,
            "stations": [],
            "error": "no live data available — have the collectors been running?",
            "mode_performance": LIVE_PERFORMANCE,
        }

    actual_ts = df["ts"].iloc[0] if "ts" in df.columns else t
    cold = cold_start_check()

    # In live mode ALL stations are treated as onset candidates (we have no
    # live depth sensor to say "already flooded"), so every station gets a
    # prediction. The model handles NaN fl_* features natively.
    prob = b.predict(df)
    raw = b.raw_score(df)

    out = []
    for i, r in enumerate(df.itertuples()):
        alert = bool(raw[i] >= b.threshold)
        out.append({
            "station_code": r.station_code,
            "district": getattr(r, "district", None),
            "depth_now_cm": None,  # no live sensor
            "status": "at_risk" if alert else "clear",
            "alert": alert,
            "probability": round(float(prob[i]), 5) if np.isfinite(prob[i]) else None,
            "predicted_depth_cm": None,
            "live_note": "No live flood sensor — depth unknown.",
        })

    n_alert = sum(o["alert"] for o in out)
    out = _json_safe(out)
    return {
        "timestamp": str(actual_ts),
        "data_mode": LIVE_MODE,
        "live_note": "Live predictions from public API data. "
                     "Catches about 1 flood in 20.",
        "tier_cm": b.tier_cm,
        "horizon_hours": b.horizon_h,
        "model": bundle_name,
        "cold_start": cold["cold_start"],
        "mode_performance": LIVE_PERFORMANCE,
        "sources": ["thaiwater", "openmeteo_gfs"],
        "missing_sources": ["bma_rain_gauges", "bma_road_flood_sensors",
                            "bma_canal_full_network"],
        "stations": out,
        "counts": {
            "total": len(out),
            "alerting": int(n_alert),
            "flooded_now": 0,  # no live sensor to know
            "sensor_offline": 0,
        },
        "caveats": _live_caveats(),
    }


def district_risk(ts: Optional[str] = None, mode: str = "replay",
                  **kw) -> Dict[str, object]:
    """Roll the station forecast up to districts, for the map.

    The share of a district's stations alerting is the honest unit here, and it
    should be read with Phase 5's finding beside it: when a district genuinely
    floods, only about 35% of its stations do. A district colour is a summary of
    a few points, not a flood extent, and `is_flood_extent: false` says so in
    the payload.
    """
    f = forecast_at(ts, mode=mode, **kw)
    if not f.get("stations"):
        return f
    d = pd.DataFrame(f["stations"])
    g = d.groupby("district").agg(
        stations=("station_code", "count"),
        alerting=("alert", "sum"),
        flooded_now=("status", lambda s: int((s == "flooded_now").sum())),
        max_depth_cm=("depth_now_cm", "max"),
        max_probability=("probability", "max"),
    ).reset_index()
    g["share_alerting"] = (g.alerting / g.stations).round(3)
    g["level"] = pd.cut(g.share_alerting, [-0.01, 0.0, 0.34, 0.67, 1.0],
                        labels=["none", "low", "moderate", "high"]).astype(str)
    data_mode = _data_mode(mode)
    result = {
        "timestamp": f["timestamp"], "data_mode": data_mode,
        "districts": _json_safe(g.to_dict(orient="records")),
        "is_flood_extent": False,
        "extent_note": "Shares are over the handful of sensors in each district, "
                       "not a mapped flood extent. When a district floods, "
                       "typically only about a third of its sensors register it.",
        "caveats": f.get("caveats", response_caveats()),
    }
    if mode == "live":
        result["mode_performance"] = f.get("mode_performance")
        result["cold_start"] = f.get("cold_start")
    return result


# ---------------------------------------------------------------------------
# Caveats and the model card
# ---------------------------------------------------------------------------
def response_caveats() -> List[str]:
    """The short list that rides along with every prediction response."""
    return [
        "Historical replay, not a live feed.",
        "Roughly 84% of alerts at this threshold do not become floods.",
        "Typical warning time is about 15 minutes — one measurement step.",
        "Station coordinates are district centroids: all sensors in a district "
        "share one point.",
        "Predicted depth is not served — the depth intervals failed their "
        "coverage check.",
    ]


def model_card(bundle_name: str = "onset_t15_h1_final") -> Dict[str, object]:
    """Everything a reasonable person would want before trusting this.

    Served at an endpoint rather than written in a PDF, because a limitation
    that is not in the response will not be read. The numbers are from Phases 4
    and 5 and are reproducible from `docs/reports/`.
    """
    b = load_bundle(bundle_name)
    cfg = load_config()
    return {
        "model": bundle_name,
        "kind": b.kind,
        "question_answered": (
            "This road is below {t} cm now — will it reach {t} cm within "
            "{h} hour(s)?".format(t=b.tier_cm, h=b.horizon_h)),
        "trained_on_years": b.meta["fold"]["train"],
        "validated_on": b.meta["fold"]["val"],
        "tested_on": b.meta["fold"]["test"],
        "features": b.meta["n_features"],
        "performance": {
            "event_pod": 0.53,
            "event_pod_note": "share of real floods flagged before the water "
                              "arrived, test year 2025",
            "recall_on_dry_roads": 0.23,
            "precision": 0.16,
            "median_warning_minutes": 15,
            "share_of_detections_with_one_step_warning": 0.75,
            "alert_episodes_per_flood_warned": 6.6,
        },
        "compared_with": {
            "simple_rain_threshold_recall_on_dry_roads": 0.22,
            "note": "The model beats a district rainfall threshold by about one "
                    "percentage point. The limit is the data, not the method.",
        },
        "known_limitations": [
            "RESOLUTION: when a district floods, only ~35% of its stations do, "
            "yet every rainfall, terrain and canal feature is identical across "
            "them. The system cannot say which road in a district will flood.",
            "TERRAIN contributes 0% of model gain, because elevation is a "
            "district average. This is fixable only with station coordinates.",
            "DEPTH is not predicted. Intervals covered 43-63% of wet rows "
            "against a 90% target.",
            "CANAL water level and flow are citywide averages: only 13 of 33 "
            "and 3 of 33 districts are reachable by station code.",
            "PUMP and gate operations are invisible. A flood a pump prevented "
            "is recorded as no flood.",
            "TIDE is astronomical phase only, with no measured height.",
            "The model is mildly UNDER-confident after calibration; predicted "
            "probabilities run about half the observed rate.",
        ],
        "would_most_improve_it": [
            "Station coordinates for the 300 water-level and 30 flow sensors",
            "Weather radar (gauges are ~1 per 12 km2; storm cells are 2-5 km)",
            "Pump and gate operating status",
            "A Chao Phraya tide gauge",
        ],
        "alerting": {
            "cap_status": cfg["alerting"]["cap_status"],
            "authorised_for_public_use": cfg["alerting"]["cap_status"] == "Actual",
            "note": "cap_status stays 'Test' until BMA authorises in writing.",
        },
        "data_mode": DATA_MODE_REPLAY,
    }


# ---------------------------------------------------------------------------
# CAP
# ---------------------------------------------------------------------------
def cap_alert(station: Dict[str, object], timestamp: str,
              tier_cm: int, horizon_h: int) -> Dict[str, object]:
    """A CAP 1.2 payload for one station.

    `status` comes from config and is `Test`. It must not become `Actual`
    without written BMA authorisation and a named owner — an `Actual` CAP
    message is a real public warning with legal weight.

    Severity is driven by the TIER CROSSED, not by a predicted depth. Phase 5
    measured the depth intervals at 43-63% coverage against a 90% target, so
    there is no defensible depth to put in a public message.
    """
    cfg = load_config()["alerting"]
    severity = {5: "Minor", 15: "Moderate", 30: "Severe"}.get(tier_cm, "Unknown")
    return {
        "identifier": f"bkkflood-{station['station_code']}-{timestamp}",
        "sender": cfg["cap_sender"],
        "sent": timestamp,
        "status": cfg["cap_status"],
        "msgType": "Alert",
        "scope": cfg["cap_scope"],
        "info": {
            "language": cfg["languages"][0],
            "category": "Met",
            "event": "Road flooding",
            "urgency": "Expected" if horizon_h > 1 else "Immediate",
            "severity": severity,
            "certainty": "Possible",
            "headline": f"Possible road flooding at {station['station_code']} "
                        f"within {horizon_h} hour(s)",
            "description": (
                f"Water may reach {tier_cm} cm at {station['station_code']} "
                f"({station.get('district')}) within {horizon_h} hour(s). "
                f"Typical warning time is about 15 minutes and roughly 84% of "
                f"alerts do not become floods."),
            "area": {
                "areaDesc": str(station.get("district")),
                "note": "District-level only. Sensor coordinates are district "
                        "centroids, not precise locations.",
            },
            "parameter": {
                "probability": station.get("probability"),
                "tier_cm": tier_cm,
                "predicted_depth_cm": None,
                "depth_note": "Not issued: depth intervals failed coverage.",
                "data_mode": DATA_MODE_REPLAY,
            },
        },
    }


# ---------------------------------------------------------------------------
# Everything the dashboard needs beyond the forecast itself
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def district_geojson() -> Dict[str, object]:
    """Bangkok's 50 district polygons.

    The map is drawn as POLYGONS, not as station pins, and that is a data-honesty
    decision rather than a cartographic preference. Every coordinate we hold is a
    district centroid — all sensors in a district share one point — so pins would
    place several sensors on top of each other at a location where none of them
    actually is. A shaded district says exactly as much as the data supports.
    """
    import json as _json
    return _json.loads(resolve("data/gis/bangkok_districts.geojson").read_text())


def observations(ts: Optional[str] = None, hours: int = 24,
                 con=None) -> Dict[str, object]:
    """Recent rainfall, canal level and canal flow, for the monitoring panels.

    Rain is per district because rain and flood station codes share a district
    prefix. Canal level and flow are CITYWIDE — canal codes name canals, not
    districts, and only 13 of 33 and 3 of 33 flood districts are reachable by
    code. The payload says which is which in `resolution`, so a chart cannot be
    labelled "canal level in Bang Rak" by a frontend that assumed otherwise.
    """
    t = resolve_timestamp(ts)
    start = t - pd.Timedelta(hours=hours)

    owns = con is None
    con = con or connect()
    try:
        paths = _feature_paths()
        series = con.execute(f"""
            SELECT ts,
                   avg(rain_rf1hr_mean)   AS rain_mm_1h,
                   max(rain_rf1hr_max)    AS rain_mm_1h_max,
                   avg(rain_fcst_1h)      AS rain_fcst_issued_1h,
                   avg(water_rise_1h_mean) AS water_rise_1h_m,
                   avg(flow_mean)          AS flow_m3s,
                   avg(fl_depth_now)       AS mean_depth_cm,
                   max(fl_depth_now)       AS max_depth_cm,
                   count(*) FILTER (WHERE fl_depth_now >= 15) AS stations_over_15cm
            FROM read_parquet({paths})
            WHERE ts > TIMESTAMP '{start}' AND ts <= TIMESTAMP '{t}'
            GROUP BY 1 ORDER BY 1
        """).fetchdf()
        by_district = con.execute(f"""
            SELECT district, avg(rain_rf1hr_mean) AS rain_mm_1h,
                   max(rain_rf1hr_max) AS rain_mm_1h_max
            FROM read_parquet({paths})
            WHERE ts > TIMESTAMP '{start}' AND ts <= TIMESTAMP '{t}'
              AND district IS NOT NULL
            GROUP BY 1 ORDER BY 2 DESC
        """).fetchdf()
    finally:
        if owns:
            con.close()

    series = _align_forecast_to_valid_time(series)

    series["ts"] = series.ts.astype(str)
    return {
        "timestamp": str(t), "data_mode": DATA_MODE_REPLAY, "window_hours": hours,
        "series": _json_safe(series.to_dict(orient="records")),
        "rain_by_district": _json_safe(by_district.to_dict(orient="records")),
        "resolution": {
            "rain_mm_1h": "per district (gauge average)",
            "rain_fcst_mm_1h": "GFS ~13 km grid, shifted to VALID time so it "
                               "sits on the hour it describes — see "
                               "_align_forecast_to_valid_time",
            "water_rise_1h_m": "CITYWIDE average — canal codes are canal names, "
                               "not districts",
            "flow_m3s": "CITYWIDE average, excluding two river-scale gauges",
            "mean_depth_cm": "per flood station",
        },
        "caveats": response_caveats(),
    }


def _align_forecast_to_valid_time(series: pd.DataFrame) -> pd.DataFrame:
    """Move the GFS forecast onto the hour it is ABOUT, not the hour it was made.

    THE TRAP THIS AVOIDS. `rain_fcst_1h` at time t is the rain the weather model
    expected over `(t, t+1h]` — see `features.py`. The gauge column
    `rain_rf1hr_mean` at time t is rain that already fell over `(t-1h, t]`.
    Plotted against each other at the same x, they are describing DIFFERENT
    HOURS, offset by one.

    Nothing about that looks wrong on a chart. Two rain traces, both plausible,
    apparently disagreeing — and every conclusion drawn from the picture is
    about an artefact of the alignment rather than about GFS. It would tend to
    make the forecast look worse than it is during a rising storm and better
    during a falling one.

    So the forecast is shifted forward by one hour onto its VALID time, and the
    chart then compares the two numbers that genuinely describe the same hour of
    weather. `rain_fcst_issued_1h` is kept alongside, unshifted, because the
    question "what did we believe at the time" is a different and also-valid
    one.
    """
    if series.empty or "rain_fcst_issued_1h" not in series.columns:
        return series

    valid = series[["ts", "rain_fcst_issued_1h"]].copy()
    valid["ts"] = valid["ts"] + pd.Timedelta(hours=1)
    valid = valid.rename(columns={"rain_fcst_issued_1h": "rain_fcst_mm_1h"})
    return series.merge(valid, on="ts", how="left")


def station_history(station_code: str, ts: Optional[str] = None, hours: int = 24,
                    con=None) -> Dict[str, object]:
    """One station's recent depth and its district's rain, for the detail chart.

    Both series are OBSERVED history. No forecast line is returned: the model
    produces a probability, not a depth trajectory, and drawing a predicted curve
    beside a measured one would imply a precision the system does not have.
    """
    t = resolve_timestamp(ts)
    start = t - pd.Timedelta(hours=hours)

    owns = con is None
    con = con or connect()
    try:
        paths = _feature_paths()
        df = con.execute(f"""
            SELECT ts, district, fl_depth_now AS depth_cm,
                   rain_rf1hr_mean AS rain_mm_1h
            FROM read_parquet({paths})
            WHERE station_code = '{station_code}'
              AND ts > TIMESTAMP '{start}' AND ts <= TIMESTAMP '{t}'
            ORDER BY ts
        """).fetchdf()
    finally:
        if owns:
            con.close()

    if df.empty:
        return {"station_code": station_code, "error": "no data", "series": []}
    df["ts"] = df.ts.astype(str)
    cfg = load_config()["flood_event"]["tiers_cm"]
    return {
        "station_code": station_code,
        "district": df.district.iloc[-1],
        "timestamp": str(t), "data_mode": DATA_MODE_REPLAY, "window_hours": hours,
        "tiers_cm": {k: int(v) for k, v in cfg.items()},
        "series": _json_safe(df.drop(columns=["district"]).to_dict(orient="records")),
        "note": "Observed history only. No forecast trajectory is drawn — the "
                "model outputs a probability, not a depth curve.",
    }


def hotspots(top: int = 20, con=None) -> Dict[str, object]:
    """Stations that flood most often across the whole archive.

    Counted in station-hours at or above the 15 cm tier, so a single long flood
    does not outrank several separate ones as heavily as a row count would.

    Read as *where the sensors are*, not where Bangkok floods. 107 flood sensors
    cover 33 of 50 districts; a road without a sensor cannot appear here however
    often it floods.
    """
    owns = con is None
    con = con or connect()
    try:
        paths = _feature_paths()
        df = con.execute(f"""
            SELECT station_code, district,
                   count(*) FILTER (WHERE fl_depth_now >= 15) / 4.0 AS hours_over_15cm,
                   count(*) FILTER (WHERE fl_depth_now >= 30) / 4.0 AS hours_over_30cm,
                   max(fl_depth_now) AS deepest_cm,
                   min(date_part('year', ts))::INT AS first_year,
                   max(date_part('year', ts))::INT AS last_year
            FROM read_parquet({paths})
            GROUP BY 1, 2
            ORDER BY hours_over_15cm DESC
            LIMIT {top}
        """).fetchdf()
    finally:
        if owns:
            con.close()
    return {
        "data_mode": DATA_MODE_REPLAY,
        "hotspots": _json_safe(df.to_dict(orient="records")),
        "measured_in": "station-hours at or above the tier, 2019-2025",
        "coverage_note": "107 flood sensors across 33 of Bangkok's 50 districts. "
                         "A road without a sensor cannot appear here, however "
                         "often it floods.",
    }
