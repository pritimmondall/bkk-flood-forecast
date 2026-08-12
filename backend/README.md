# Backend — FastAPI service (Phase 7)

```bash
export PYTHONPATH="$PWD/src:$PWD"
uvicorn backend.app.main:app --reload
open http://127.0.0.1:8000/docs
```

## This service replays history

There is no live sensor feed. BMA's sensors are not exposed to us as an API, and
`pumps.bangkok.go.th` was deliberately not scraped. The service reads the
historical feature tables and answers *"what would the system have said at time
T"*.

Every response carries `data_mode: "replay"` and the timestamp it is answering
for. That is a field rather than a note in this file, because a caveat nobody
reads is not a caveat.

Available window: **2019-01-01 → 2025-12-31 23:45**, at 15-minute steps.
A good timestamp for demonstrating a real event: `2025-11-13 03:00:00`
(29 alerting stations, 25 already flooded).

## Endpoints

| Route | What it gives you |
|---|---|
| `GET /health` | liveness, replay window, model, `cap_status` |
| `GET /api/model-card` | **read this before integrating** |
| `GET /api/forecast` | per-station risk; `?ts=`, `?district=`, `?alerting_only=` |
| `GET /api/forecast/{station_code}` | one station |
| `GET /api/risk` | district roll-up for the map |
| `GET /api/alerts` | CAP 1.2 messages, `status: Test` |
| `GET /api/available` | replay window, for a time slider |

## Four things a client must not do

**Do not draw sensors as precise pins.** Every coordinate we hold is a district
centroid — all sensors in a district share one point.

**Do not draw district risk as a flood extent.** `is_flood_extent` is `false` in
the payload. When a district genuinely floods, only about 35% of its sensors
register it; a district colour summarises a handful of points.

**Do not display a predicted depth.** `predicted_depth_cm` is always `null`. The
depth intervals covered 43–63% of wet rows against a 90% target, so there is no
defensible number to show. Severity comes from the tier crossed.

**Do not present alerts as reliable.** At the operating threshold roughly 84% do
not become floods, and typical warning time is about 15 minutes.

## `cap_status` is `Test`

Set in `config/config.yaml`. It must not become `Actual` without written BMA
authorisation and a named owner — an `Actual` CAP message is a real public
warning with legal weight. Guarded by `tests/test_serving.py`.

## Where the logic lives

`src/bkkflood/serving.py`. This package is routing and error handling only. If a
bug can be reproduced without a web server, it belongs in the library.
