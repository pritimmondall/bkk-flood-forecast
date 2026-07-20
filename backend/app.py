#!/usr/bin/env python3
"""BKK Flood Forecast prediction service (FastAPI).

Serves the model->dashboard output contract from the saved artifacts:
per station x horizon (1h/3h/6h): calibrated risk % per tier (5/15/30cm),
depth quantiles (P05..P95), alert flags, and derived KPIs.

Demo mode: features are read from the prebuilt training-set parquet
(data/training/<split>.parquet), so any timestamp inside that split can be
"replayed" as if it were live. In production the same endpoints sit on top
of a live feature builder against PostGIS — the response contract does not
change (that is the point of the contract).

Serving policy (decided on val-2024, frozen — see eval_summary.json):
  ge5 / ge15 (all horizons) and ge30@6h : hybrid = model>=val-threshold OR
                                          depth_now >= tier
  ge30 @ 1h/3h                          : persistence only (standalone
                                          classifier unusable; GRU is the
                                          documented phase-2 fix)
Risk % shown = isotonic-calibrated probability (calibrators.joblib).

Run:
  pip install fastapi uvicorn
  uvicorn backend.app:app --port 8000            # from repo root
  SERVE_SPLIT=val uvicorn backend.app:app        # replay 2024 instead

Endpoints: /health  /stations  /range  /forecast  /forecast/area  /cap
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "models" / "artifacts"
TRAINING_DIR = ROOT / "data" / "training"
SPLIT = os.environ.get("SERVE_SPLIT", "test")

HORIZONS = [1, 3, 6]
TIERS = [5, 15, 30]
QUANTILES = [5, 25, 50, 75, 95]
PERSISTENCE_ONLY = {(30, 1), (30, 3)}     # tier-30 short horizons

app = FastAPI(title="BKK Flood Forecast API", version="0.1.0",
              description="Model output contract for the BMA flood dashboard. "
              "Prototype — alerts are CAP status=Test only.")

# The Vite dashboard runs on a different local origin during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(","),
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Artifacts + replay data (loaded once at startup)
# ---------------------------------------------------------------------------

def _model_only_metadata() -> tuple[dict, list[str]]:
    """Recover the serving schema from a LightGBM text artifact.

    This keeps the live, rain-driven endpoint usable when the large training
    parquet files were intentionally excluded from a deployment bundle.
    """
    text = (ARTIFACTS / "clf_ge15_1h.txt").read_text(encoding="utf-8")
    feature_line = next(line for line in text.splitlines()
                        if line.startswith("feature_names="))
    features = feature_line.removeprefix("feature_names=").split()
    categories_line = next(line for line in text.splitlines()
                           if line.startswith("pandas_categorical:"))
    categories = json.loads(categories_line.split(":", 1)[1])[0]
    return {"features": [f for f in features if f != "station_code"],
            "cadence_min": None}, categories


FEATURES_FILE = TRAINING_DIR / "features.json"
REPLAY_AVAILABLE = FEATURES_FILE.exists() and (TRAINING_DIR / f"{SPLIT}.parquet").exists()
if REPLAY_AVAILABLE:
    _meta = json.loads(FEATURES_FILE.read_text())
    _model_stations: list[str] = []
else:
    _meta, _model_stations = _model_only_metadata()

FEATURES = _meta["features"] + ["station_code"]
_ev = json.loads((ARTIFACTS / "eval_summary.json").read_text())
THRESHOLDS = _ev["thresholds"]
CALIBRATORS = joblib.load(ARTIFACTS / "calibrators.joblib")
CLF = {(t, h): lgb.Booster(model_file=str(ARTIFACTS / f"clf_ge{t}_{h}h.txt"))
       for t in TIERS for h in HORIZONS}
REG = {(q, h): lgb.Booster(model_file=str(ARTIFACTS / f"reg_q{q:02d}_{h}h.txt"))
       for q in QUANTILES for h in HORIZONS}


def _load_replay() -> pd.DataFrame:
    cols = ["station_code", "site_timestamp"] + _meta["features"]
    table = pq.read_table(TRAINING_DIR / f"{SPLIT}.parquet", columns=cols)
    schema = pa.schema([pa.field(f.name, pa.float32())
                        if f.type == pa.float64() else f for f in table.schema])
    df = table.cast(schema).to_pandas(self_destruct=True)
    df["station_code"] = df["station_code"].astype(str)
    return df.sort_values("site_timestamp").reset_index(drop=True)


if REPLAY_AVAILABLE:
    DATA = _load_replay()
    TS_VALUES = DATA["site_timestamp"].to_numpy()
    STATIONS = sorted(DATA["station_code"].unique())
else:
    DATA = pd.DataFrame()
    TS_VALUES = np.array([], dtype="datetime64[ns]")
    STATIONS = sorted(_model_stations)


def _load_coords() -> dict[str, tuple[float, float]]:
    """station_code -> (lat, lon) from the geocoded registry (district/
    subdistrict centroid accuracy — see the registry's basis column)."""
    import csv
    path = ROOT / "data" / "station_registry_full.csv"
    out = {}
    if path.exists():
        with open(path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                try:
                    out[row["station_code"]] = (float(row["lat"]),
                                                float(row["lon"]),
                                                row.get("district", ""))
                except (KeyError, ValueError):
                    continue
    return out


COORDS = _load_coords()


def _add_centroid_fallbacks() -> None:
    """Use district centroids when the optional station registry is absent."""
    import csv
    path = Path(__file__).parent / "district_centroids.csv"
    centroids: dict[str, tuple[float, float]] = {}
    if path.exists():
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    centroids[row["prefix"]] = (float(row["lat"]), float(row["lon"]))
                except (KeyError, ValueError):
                    continue
    for code in STATIONS:
        if code not in COORDS:
            lat, lon = centroids.get(code.split(".")[1], (13.7563, 100.5018))
            COORDS[code] = (lat, lon, None)


_add_centroid_fallbacks()


def _rows_at(ts: pd.Timestamp) -> pd.DataFrame:
    if not REPLAY_AVAILABLE:
        raise HTTPException(503, "replay data is not installed; use /forecast/live")
    lo = np.searchsorted(TS_VALUES, np.datetime64(ts), side="left")
    hi = np.searchsorted(TS_VALUES, np.datetime64(ts), side="right")
    return DATA.iloc[lo:hi]


# ---------------------------------------------------------------------------
# Core prediction
# ---------------------------------------------------------------------------

def predict_at(ts: pd.Timestamp) -> list[dict]:
    rows = _rows_at(ts)
    if rows.empty:
        raise HTTPException(404, f"no data at {ts} in split '{SPLIT}' "
                                 f"(range: /range)")
    return predict_rows(rows)


def predict_rows(rows: pd.DataFrame) -> list[dict]:
    X = rows.copy()
    X["station_code"] = X["station_code"].astype("category")
    feats = X[FEATURES]
    depth_now = np.nan_to_num(rows["fl_depth_now"].to_numpy(), nan=0.0)

    risk_raw = {(t, h): CLF[(t, h)].predict(feats)
                for t in TIERS for h in HORIZONS}
    depth_q = {(q, h): np.maximum(REG[(q, h)].predict(feats), 0.0)
               for q in QUANTILES for h in HORIZONS}

    out = []
    for i, code in enumerate(rows["station_code"]):
        horizons = {}
        for h in HORIZONS:
            tiers_out, alerts = {}, {}
            for t in TIERS:
                raw = float(risk_raw[(t, h)][i])
                cal = float(CALIBRATORS[f"ge{t}_{h}h"].predict([raw])[0])
                if (t, h) in PERSISTENCE_ONLY:
                    alert = bool(depth_now[i] >= t)
                else:
                    alert = bool(raw >= THRESHOLDS[f"ge{t}_{h}h"]
                                 or depth_now[i] >= t)
                tiers_out[f"ge{t}cm"] = round(cal * 100, 2)
                alerts[f"ge{t}cm"] = alert
            horizons[f"{h}h"] = {
                "risk_pct": tiers_out,
                "alert": alerts,
                "depth_cm": {f"p{q:02d}": round(float(depth_q[(q, h)][i]), 1)
                             for q in QUANTILES},
            }
        coord = COORDS.get(code)
        out.append({
            "station_code": code,
            "district_prefix": code.split(".")[1],
            "district": coord[2] if coord else None,
            "lat": coord[0] if coord else None,
            "lon": coord[1] if coord else None,
            "depth_now_cm": round(float(depth_now[i]), 1),
            "horizons": horizons,
            "kpi": _kpis(horizons, depth_now[i]),
        })
    return out


def _kpis(horizons: dict, depth_now: float) -> dict:
    """Derived KPI chips — dashboard reads these, never recomputes them."""
    risks = {h: horizons[f"{h}h"]["risk_pct"]["ge15cm"] for h in HORIZONS}
    p95s = {h: horizons[f"{h}h"]["depth_cm"]["p95"] for h in HORIZONS}
    peak_h = max(risks, key=risks.get)
    peak_depth_h = max(p95s, key=p95s.get)
    alert_hs = [h for h in HORIZONS if horizons[f"{h}h"]["alert"]["ge15cm"]]
    return {
        "peak_risk_pct": risks[peak_h],
        "peak_risk_time_h": peak_h,
        "time_to_warning_h": min(alert_hs) if alert_hs else None,
        "peak_depth_p95_cm": p95s[peak_depth_h],
        "peak_depth_time_h": peak_depth_h,
        "time_to_15cm_h": next((h for h in HORIZONS if p95s[h] >= 15), None),
        "time_to_30cm_h": next((h for h in HORIZONS if p95s[h] >= 30), None),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/docs")


@app.get("/map", include_in_schema=False)
def map_page():
    """Leaflet map over /forecast/live (falls back to a replay timestamp)."""
    from fastapi.responses import FileResponse
    return FileResponse(Path(__file__).parent / "map.html",
                        media_type="text/html")


@app.get("/health")
def health():
    return {"status": "ok", "split": SPLIT, "stations": len(STATIONS),
            "models": len(CLF) + len(REG), "replay_available": REPLAY_AVAILABLE}


@app.get("/stations")
def stations():
    return [{"station_code": s, "district_prefix": s.split(".")[1]}
            for s in STATIONS]


@app.get("/range")
def ts_range():
    if not REPLAY_AVAILABLE:
        raise HTTPException(503, "replay data is not installed; /range is unavailable")
    return {"split": SPLIT,
            "min_ts": str(pd.Timestamp(TS_VALUES[0])),
            "max_ts": str(pd.Timestamp(TS_VALUES[-1])),
            "cadence_min": _meta["cadence_min"]}


def to_geojson(preds: list[dict], meta: dict) -> dict:
    """FeatureCollection for direct Leaflet use: L.geoJSON(data, ...)."""
    feats = []
    for p in preds:
        if p.get("lat") is None:
            continue
        props = {k: v for k, v in p.items() if k not in ("lat", "lon")}
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point",
                                   "coordinates": [p["lon"], p["lat"]]},
                      "properties": props})
    return {"type": "FeatureCollection", "metadata": meta, "features": feats}


@app.get("/forecast")
def forecast(ts: str = Query(..., description="e.g. 2025-09-15T14:00:00"),
             station: Optional[str] = None,
             format: str = Query("json", description="json | geojson")):
    stamp = pd.Timestamp(ts)
    preds = predict_at(stamp)
    if station:
        preds = [p for p in preds if p["station_code"] == station]
        if not preds:
            raise HTTPException(404, f"station {station} not found at {stamp}")
    if format == "geojson":
        return to_geojson(preds, {"ts": str(stamp), "split": SPLIT})
    return {"ts": str(stamp), "split": SPLIT, "stations": preds}


@app.get("/forecast/area")
def forecast_area(ts: str, prefix: str):
    """Area aggregation: P95 across the district's stations is the PRIMARY
    displayed line (supervisor rule); mean is secondary."""
    preds = [p for p in predict_at(pd.Timestamp(ts))
             if p["district_prefix"] == prefix]
    if not preds:
        raise HTTPException(404, f"no stations with prefix {prefix}")
    agg = {}
    for h in HORIZONS:
        risks = [p["horizons"][f"{h}h"]["risk_pct"]["ge15cm"] for p in preds]
        p95s = [p["horizons"][f"{h}h"]["depth_cm"]["p95"] for p in preds]
        agg[f"{h}h"] = {
            "risk_pct_p95_primary": round(float(np.percentile(risks, 95)), 2),
            "risk_pct_mean_secondary": round(float(np.mean(risks)), 2),
            "depth_p95_max_cm": round(float(np.max(p95s)), 1),
            "stations_alerting": sum(
                p["horizons"][f"{h}h"]["alert"]["ge15cm"] for p in preds),
        }
    return {"ts": ts, "district_prefix": prefix,
            "n_stations": len(preds), "horizons": agg}


@app.get("/forecast/live")
def forecast_live(station: Optional[str] = None,
                  format: str = Query("json", description="json | geojson")):
    """LIVE mode: rain from Open-Meteo right now; BMA sensor features are
    marked missing (same as a sensor outage in training). Rain+climatology
    driven — weaker than replay mode at 1h, and persistence alerts cannot
    fire. See backend/live.py docstring for the full caveats."""
    from backend.live import build_live_rows, write_default_centroids
    prefixes = sorted({s.split(".")[1] for s in STATIONS})
    write_default_centroids(prefixes)
    now = pd.Timestamp.now(tz="Asia/Bangkok").tz_localize(None)
    now = now.floor("15min")
    try:
        rows = build_live_rows(STATIONS, _meta["features"], now)
    except Exception as e:                       # network / API failure
        raise HTTPException(503, f"live weather fetch failed: {e}")
    preds = predict_rows(rows)
    if station:
        preds = [p for p in preds if p["station_code"] == station]
        if not preds:
            raise HTTPException(404, f"unknown station {station}")
    rain_used = {p: round(rows.loc[rows.station_code.astype(str).str
                          .contains(f".{p}.", regex=False),
                          "rain_rf1hr_mean"].iloc[0], 2)
                 for p in prefixes} if not station else None
    if format == "geojson":
        return to_geojson(preds, {"ts": str(now), "mode": "live-degraded"})
    return {"ts": str(now), "mode": "live-degraded",
            "data_sources": {"rain": "open-meteo.com (10-min cache)",
                             "bma_sensors": "not connected — features "
                                            "treated as sensor-out"},
            "rain_rf1hr_by_district_mm": rain_used,
            "stations": preds}


@app.get("/cap")
def cap_alert(ts: str, station: str):
    """CAP 1.2 alert XML for one station at one timestamp (status=Test)."""
    from backend.cap import build_cap
    preds = [p for p in predict_at(pd.Timestamp(ts))
             if p["station_code"] == station]
    if not preds:
        raise HTTPException(404, f"station {station} not found at {ts}")
    xml = build_cap(preds[0], pd.Timestamp(ts))
    if xml is None:
        return {"station": station, "ts": ts,
                "cap": None, "reason": "no alert condition at any horizon"}
    from fastapi.responses import Response
    return Response(content=xml, media_type="application/xml")
