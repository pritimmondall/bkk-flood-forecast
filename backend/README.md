# BKK Flood Forecast — Backend API

FastAPI service that serves the flood-forecast model to the dashboard. It exposes
per-station flood risk and depth predictions at 1h / 3h / 6h horizons, in JSON or
map-ready GeoJSON, plus CAP alert generation and a built-in demo map.

---

## 1. Setup

**Requirements:** Python 3.10+, and the trained artifacts in `models/artifacts/`
and the feature parquet in `data/training/` (produced by `data_pipeline/`).

```bash
# from the repository root
pip install fastapi uvicorn lightgbm scikit-learn joblib pandas pyarrow numpy requests

# start the server
uvicorn backend.app:app --port 8000
```

Open **http://127.0.0.1:8000/** — it redirects to the interactive API docs (`/docs`),
where every endpoint can be tried in the browser.

**Two data modes:**

| Mode | Source | How to select |
|------|--------|---------------|
| Replay (default) | prebuilt 2025 test parquet | `SERVE_SPLIT=test` (default) |
| Replay 2024 | validation parquet | `SERVE_SPLIT=val uvicorn backend.app:app` |
| Live | Open-Meteo rain, now | the `/forecast/live` endpoint |

Replay lets any timestamp inside the split be served as if it were live — used for
the demo and for testing. Live mode fetches current Bangkok rain; BMA sensor
features are marked offline until a real-time feed is connected.

---

## 2. Endpoints

Base URL: `http://127.0.0.1:8000`

### `GET /health`
Service status. No parameters.
```json
{ "status": "ok", "split": "test", "stations": 100, "models": 24 }
```

### `GET /stations`
List of all served stations with their district prefix.

### `GET /range`
Valid timestamp range for the current replay split (min, max, cadence in minutes).
Use this to know which `ts` values `/forecast` accepts.

### `GET /forecast`  — main endpoint
Prediction for every station (or one) at a given replay timestamp.

| Param | Required | Description |
|-------|----------|-------------|
| `ts` | yes | timestamp, e.g. `2025-11-13T03:00:00` (within `/range`) |
| `station` | no | limit to one station, e.g. `FL.SMI.01` |
| `format` | no | `json` (default) or `geojson` |

```
GET /forecast?ts=2025-11-13T03:00:00
GET /forecast?ts=2025-11-13T03:00:00&station=FL.SMI.01
GET /forecast?ts=2025-11-13T03:00:00&format=geojson      ← for Leaflet
```

### `GET /forecast/live`
Same output as `/forecast`, but fed by **real-time Open-Meteo rain** for "now".
BMA sensor features are offline → rain + climatology driven (weaker at 1h). No `ts`.

| Param | Required | Description |
|-------|----------|-------------|
| `station` | no | limit to one station |
| `format` | no | `json` (default) or `geojson` |

```
GET /forecast/live
GET /forecast/live?format=geojson
```
First call takes ~30–60s (33 district weather queries + models); cached ~10 min.

### `GET /forecast/area`
District-level aggregation. **P95 across the district's stations is the primary
displayed line; mean is secondary** (supervisor rule).

| Param | Required | Description |
|-------|----------|-------------|
| `ts` | yes | timestamp |
| `prefix` | yes | district code, e.g. `SMI`, `CTC`, `DDG` |

```
GET /forecast/area?ts=2025-11-13T03:00:00&prefix=RTW
```

### `GET /cap`
CAP 1.2 alert XML for one station at one timestamp. Returns XML if any tier
alerts, or `{"cap": null}` if not. Status is always `Test`.

| Param | Required | Description |
|-------|----------|-------------|
| `ts` | yes | timestamp |
| `station` | yes | station code |

```
GET /cap?ts=2025-11-13T03:00:00&station=FL.RTW.08
```

### `GET /map`
Built-in Leaflet demo map (HTML). Loads live mode by default; a text box switches
to a replay timestamp. Not the production dashboard — a quick visual check.

### `GET /docs`
Auto-generated interactive API documentation (Swagger UI).

---

## 3. Response contract (`/forecast`)

```jsonc
{
  "ts": "2025-11-13 03:00:00",
  "split": "test",
  "stations": [
    {
      "station_code": "FL.RTW.08",
      "district_prefix": "RTW",
      "district": "Ratchathewi",
      "lat": 13.763, "lon": 100.530,
      "depth_now_cm": 37.0,
      "horizons": {
        "1h": {
          "risk_pct": { "ge5cm": 99.1, "ge15cm": 92.0, "ge30cm": 71.0 },
          "alert":    { "ge5cm": true, "ge15cm": true, "ge30cm": true },
          "depth_cm": { "p05": 30.1, "p25": 34.7, "p50": 36.5,
                        "p75": 39.2, "p95": 47.7 }
        },
        "3h": { ... },
        "6h": { ... }
      },
      "kpi": {
        "peak_risk_pct": 92.0, "peak_risk_time_h": 1,
        "time_to_warning_h": 1, "peak_depth_p95_cm": 47.7,
        "peak_depth_time_h": 1, "time_to_15cm_h": 1, "time_to_30cm_h": 1
      }
    }
  ]
}
```

**Field meanings**
- `risk_pct` — calibrated probability (%) of reaching each tier, per horizon.
- `alert` — boolean, after the serving policy is applied (see below). This is what
  the dashboard should color markers on, **not** a raw threshold on `risk_pct`.
- `depth_cm` — predicted flood depth quantiles P05–P95. **P95 is the value to
  display** as the "worst-case" line.
- `kpi` — derived fields so the dashboard never recomputes: peak risk and when,
  time until first alert, peak P95 depth, time until 15cm / 30cm (null if never).
- `depth_now_cm` — current measured depth (a feature, not a prediction).

**GeoJSON form** (`format=geojson`) — a `FeatureCollection`; each station is a
`Point` with `[lon, lat]` and the full record (minus lat/lon) in `properties`.
Drop-in for `L.geoJSON(data)`.

---

## 4. Serving policy (baked into the `alert` flags)

Alerts are not a raw threshold — they follow the policy frozen on 2024 validation:

| Tier / horizon | Rule |
|----------------|------|
| ≥5cm, ≥15cm (all horizons); ≥30cm @6h | **Hybrid**: model ≥ val-threshold **OR** depth already ≥ tier |
| ≥30cm @1h, @3h | **Persistence only** — the standalone classifier is unusable at these; GRU is the documented fix |

`risk_pct` is the isotonic-calibrated probability, safe to show as a real %.

---

## 5. Dashboard integration (Leaflet)

```js
const res  = await fetch("http://127.0.0.1:8000/forecast/live?format=geojson");
const data = await res.json();

L.geoJSON(data, {
  pointToLayer: (f, latlng) => {
    const h1 = f.properties.horizons["1h"];
    const color = h1.alert.ge15cm ? "red" : h1.alert.ge5cm ? "orange" : "green";
    return L.circleMarker(latlng, { radius: 7, color, fillOpacity: 0.7 })
      .bindPopup(
        `<b>${f.properties.station_code}</b> — ${f.properties.district}<br>` +
        `1h ≥15cm risk: ${h1.risk_pct.ge15cm}%<br>` +
        `P95 depth: ${h1.depth_cm.p95} cm<br>` +
        `peak risk: ${f.properties.kpi.peak_risk_pct}% @ ${f.properties.kpi.peak_risk_time_h}h`
      );
  }
}).addTo(map);
```

For district views call `/forecast/area?...&prefix=XXX` and plot
`risk_pct_p95_primary`.

---

## 6. Notes & limits

- **Coordinates** are district/subdistrict-centroid accuracy (~1–2 km); stations in
  the same district may overlap on the map — consider clustering or jitter.
- **Live mode** runs without BMA sensor feeds — rain-driven; persistence alerts
  cannot fire; key live alerts on the ≥15cm tier.
- **CAP** messages are always `status=Test`; they format alerts but do not send.
- The response **contract is stable** — future model upgrades (live sensors, GRU,
  nearest-canal features) change nothing the dashboard consumes.

Good demo timestamps: `2025-11-13T03:00:00` (citywide storm, 25 stations flooding)
vs `2025-01-01T00:00:00` (fully dry). Full field-level detail is in
`docs/BKK_Flood_Forecast_ML_Documentation.docx`.
