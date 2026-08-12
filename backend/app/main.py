"""
FastAPI service for the Bangkok flood forecast. Phase 7.

Deliberately thin. Everything testable lives in `bkkflood.serving`; this file
is routing, validation and error handling. If a bug can be reproduced without
starting a web server, it belongs in the library and not here.

--------------------------------------------------------------------------
THE RULE THIS SERVICE IS BUILT AROUND
--------------------------------------------------------------------------
Every caveat is a FIELD, never a footnote (project rule 6). Each prediction
response carries `data_mode`, a `caveats` list and — where relevant — an
explicit `null` for things we refuse to predict, such as depth. A limitation
recorded only in a document will not be read by whoever integrates this.

Run it:
    export PYTHONPATH="$PWD/src"
    uvicorn backend.app.main:app --reload
    open http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_root = Path(__file__).resolve().parents[2]
if str(_root / "src") not in sys.path:
    sys.path.insert(0, str(_root / "src"))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from bkkflood.config import load_config
from bkkflood.serving import (available_range, cap_alert, district_geojson,
                              district_risk, forecast_at, hotspots, load_bundle,
                              model_card, observations, response_caveats,
                              station_history)
from bkkflood.live import live_status as _live_status

CFG = load_config()

app = FastAPI(
    title="Bangkok Flood Forecast",
    version="3.0.0",
    description=(
        "Road-flood forecasting for the Bangkok Metropolitan Administration.\n\n"
        "**This service replays history.** There is no live sensor feed, so every "
        "response carries `data_mode: \"replay\"` and the timestamp it is "
        "answering for.\n\n"
        "**Read `/api/model-card` before integrating.** At the operating "
        "threshold roughly 84% of alerts do not become floods, typical warning "
        "time is about 15 minutes, and predicted depth is deliberately not "
        "served."
    ),
)

# The frontend is served separately in development.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/", include_in_schema=False)
def root():
    """Send a browser to the interactive docs.

    Without this, opening the service root returns FastAPI's bare
    `{"detail":"Not Found"}` — which is correct and looks exactly like a broken
    server to anyone who did not write it. The first thing a new integrator does
    is open the root URL.
    """
    return RedirectResponse("/docs")


@app.get("/api", tags=["meta"])
def api_index():
    """A plain list of what this service offers, for humans and for scripts."""
    return {
        "service": "Bangkok Flood Forecast",
        "version": app.version,
        "data_mode": "replay",
        "start_here": "/api/model-card",
        "interactive_docs": "/docs",
        "endpoints": {
            "GET /health": "liveness, replay window, model, cap_status",
            "GET /api/model-card": "what the model can and cannot do — read first",
            "GET /api/available": "replay window and cadence, for a time slider",
            "GET /api/forecast": "per-station risk (?ts=, ?district=, ?alerting_only=)",
            "GET /api/forecast/{station_code}": "one station",
            "GET /api/risk": "district roll-up for the map",
            "GET /api/alerts": "CAP 1.2 messages (status: Test)",
        },
        "try_this": "/api/forecast?ts=2025-11-13 03:00:00&alerting_only=true",
        "try_this_note": "a real flood event: 29 stations alerting, 25 already flooded",
    }


@app.get("/health", tags=["meta"])
def health():
    """Liveness, plus the window the service can actually answer for."""
    try:
        rng = available_range()
        bundle = load_bundle()
        return {"status": "ok", "data_mode": "replay", "available": rng,
                "model": bundle.name, "tier_cm": bundle.tier_cm,
                "horizon_hours": bundle.horizon_h,
                "cap_status": CFG["alerting"]["cap_status"]}
    except Exception as e:                       # pragma: no cover
        raise HTTPException(503, f"not ready: {type(e).__name__}: {e}")


@app.get("/api/model-card", tags=["meta"])
def api_model_card():
    """What this model can and cannot do, with the measured numbers.

    Served as an endpoint rather than kept in a PDF, on the principle that a
    limitation which is not in the response will not be read.
    """
    return model_card()


@app.get("/api/forecast", tags=["forecast"])
def api_forecast(
    ts: Optional[str] = Query(None, description="ISO timestamp; latest if omitted"),
    district: Optional[str] = Query(None),
    alerting_only: bool = Query(False),
    mode: str = Query("replay", description="'replay' for historical, 'live' for real-time"),
):
    """Per-station risk at one moment.

    Stations already at or above the tier come back as `flooded_now` with a
    `null` probability. An onset model is being served and it never saw
    already-flooded rows in training, so it has no opinion worth reporting on
    them — reporting one anyway would be inventing a number.

    In live mode (`mode=live`), predictions use collected API data. Measured
    at ~5% event POD — see `mode_performance` in the response.
    """
    out = forecast_at(ts, mode=mode)
    if "error" in out:
        if mode == "live":
            raise HTTPException(503, out["error"])
        raise HTTPException(404, out["error"] + f" (available: {out.get('available', '')})")
    if district:
        out["stations"] = [s for s in out["stations"]
                           if (s["district"] or "").lower() == district.lower()]
    if alerting_only:
        out["stations"] = [s for s in out["stations"] if s["alert"]]
    out["returned"] = len(out["stations"])
    return out


@app.get("/api/forecast/{station_code}", tags=["forecast"])
def api_forecast_station(station_code: str, ts: Optional[str] = None):
    out = forecast_at(ts)
    if "error" in out:
        raise HTTPException(404, out["error"])
    match = [s for s in out["stations"] if s["station_code"] == station_code]
    if not match:
        raise HTTPException(404, f"unknown station {station_code}")
    return {**{k: v for k, v in out.items() if k != "stations"},
            "station": match[0]}


@app.get("/api/risk", tags=["forecast"])
def api_risk(ts: Optional[str] = None,
            mode: str = Query("replay", description="'replay' or 'live'")):
    """District roll-up for the map.

    `is_flood_extent` is `false` and stays that way. A district colour summarises
    a handful of sensors; when a district genuinely floods only about a third of
    them register it, so this is not a flood extent and must not be drawn as one.
    """
    return district_risk(ts, mode=mode)


@app.get("/api/alerts", tags=["alerting"])
def api_alerts(ts: Optional[str] = None,
              mode: str = Query("replay", description="'replay' or 'live'")):
    """CAP 1.2 messages for every alerting station.

    `status` is `Test`, from config. It must not become `Actual` without written
    BMA authorisation and a named owner — an `Actual` CAP message is a real
    public warning.

    Severity comes from the tier crossed, not from a predicted depth: the depth
    intervals failed their coverage check, so there is no defensible depth to
    put in a public message.
    """
    out = forecast_at(ts, mode=mode)
    if "error" in out:
        raise HTTPException(404, out["error"])
    b = load_bundle()
    alerts = [cap_alert(s, out["timestamp"], b.tier_cm, b.horizon_h)
              for s in out["stations"] if s["alert"]]
    return {
        "timestamp": out["timestamp"],
        "data_mode": out["data_mode"],
        "cap_status": CFG["alerting"]["cap_status"],
        "authorised_for_public_use": CFG["alerting"]["cap_status"] == "Actual",
        "count": len(alerts),
        "alerts": alerts,
        "caveats": out.get("caveats", response_caveats()),
    }


@app.get("/api/live/status", tags=["live"])
def api_live_status():
    """Collector health, coverage, cold-start state, and source capabilities.

    Check this before trusting live-mode predictions. If `cold_start` is true,
    the system has less than 24 hours of collected data and predictions are
    close to meaningless.
    """
    return _live_status()


@app.get("/api/available", tags=["meta"])
def api_available():
    """The replay window, so a client can build a time slider."""
    return {"data_mode": "replay", **available_range(),
            "cadence_minutes": CFG["data"]["model_cadence_minutes"]}


@app.get("/api/geo/districts", tags=["map"])
def api_districts():
    """Bangkok's 50 district polygons.

    The map draws POLYGONS rather than station pins. Every coordinate we hold is
    a district centroid, so pins would stack several sensors on a point where
    none of them is. A shaded district claims exactly what the data supports.
    """
    return district_geojson()


@app.get("/api/observations", tags=["monitoring"])
def api_observations(ts: Optional[str] = None,
                     hours: int = Query(24, ge=1, le=168)):
    """Rainfall, canal level and canal flow over a recent window.

    `resolution` names the spatial scale of each series. Rain is per district;
    canal level and flow are CITYWIDE, because canal station codes name canals
    rather than districts.
    """
    return observations(ts, hours)


@app.get("/api/history/{station_code}", tags=["monitoring"])
def api_history(station_code: str, ts: Optional[str] = None,
                hours: int = Query(24, ge=1, le=168)):
    """One station's observed depth and its district's rainfall."""
    out = station_history(station_code, ts, hours)
    if "error" in out:
        raise HTTPException(404, f"no data for {station_code}")
    return out


@app.get("/api/hotspots", tags=["monitoring"])
def api_hotspots(top: int = Query(20, ge=1, le=107)):
    """The stations that flood most often, 2019-2025."""
    return hotspots(top)
