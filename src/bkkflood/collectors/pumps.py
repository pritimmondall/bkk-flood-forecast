"""
BMA pump stations — `pumps.bangkok.go.th`.

--------------------------------------------------------------------------
STATUS: THE API IS DOCUMENTED AND CURRENTLY BLOCKED. NOT SCHEDULED.
--------------------------------------------------------------------------
Everything below about the endpoints is confirmed — it was read from the live
API in a browser on 2026-08-11. But the host sits behind Cloudflare bot
protection, and a plain HTTP client gets **403 Forbidden** on every path:

    GET /api/water-levels?limit=2000  ->  403
    GET /api/stations/{id}            ->  403

The browser succeeds because it passed a Cloudflare challenge; `requests` does
not. There is no robots.txt (404), so there is no stated crawl policy — but a
managed challenge is BMA's infrastructure saying "browsers only", and the
correct response to that is to ask, not to dress a script up as Chrome. Faking
browser fingerprints or reusing a `cf_clearance` cookie would be circumventing
an access control on a government system, and it would break the moment the
token expired anyway.

**So this module is not on the schedule.** The ask that unblocks it is small and
specific, which makes it the easiest thing in the whole BMA request to say yes
to.

And there is an even easier version of it: **the site has a LOGIN button.** There
is an authenticated tier above the public map, which means BMA can hand out an
account rather than change any infrastructure. "Please create us a read-only
account" is a smaller internal decision than "please allowlist this IP" — no
firewall change, no security review of an unknown address, and it is revocable
in one click. Ask for the account first; an API key or allowlist entry is the
fallback. The day that lands, add `"pumps"` and
`"pumps_stations"` back to `DEFAULT_SOURCES` in `__init__.py` — nothing else
changes, the parsers and tests are already written and green.

--------------------------------------------------------------------------
WHY A FIFTH SOURCE, WHEN THE RAIN PROBLEM IS STILL UNSOLVED
--------------------------------------------------------------------------
This one is not about improving the forecast. It is about a hole in the TRAINING
LABELS that no amount of modelling can reach.

Every label in this project is "a BMA road sensor measured >= 15 cm". A flood
that a pump station successfully prevented is therefore labelled *no flood* —
identical, in the data, to a street that was never going to flood at all. The
model is being taught that heavy rain over a well-pumped district is harmless,
when what actually happened is that someone ran the pumps. Pump activity is the
missing confounder, and there is no way to correct for it from the road sensors
alone.

Codes are shaped `PH.<DISTRICT>.NN` and **27 of the project's 33 flood-district
prefixes appear**, so this joins to our station tables almost directly.

--------------------------------------------------------------------------
WHAT THE API ACTUALLY IS (verified 2026-08-11 by reading the responses)
--------------------------------------------------------------------------
The site is a React Router app with a plain JSON API underneath. Two endpoints
matter, and they do different jobs on different clocks:

**1. `GET /api/water-levels?limit=N` — the time series.** Newest first,
paginated (`data`, `count`, `total`, `page`, `pageCount`). Fields: `id`,
`stationId`, `district`, `nameTH`, `nameEN`, `code`, `waterLevelPercent`,
`waterLevelCM`, `timestamp`.

Readings land every ~5 minutes across ~148 stations, so one hour is roughly
1,776 rows. `limit=2000` in a single request therefore captures a full hour at
FIVE-MINUTE resolution while polling only once an hour. `limit` is honoured up to
at least 2000; `pageSize`, `perPage`, `take` and `size` are all silently ignored,
which is the kind of thing that would quietly cost you 99% of your data.

`total` was **12,370,842** when checked, with the deepest pages reaching about
two weeks back. Treat it as a rolling window, not an archive: it is not seven
years of history, and what rolls off is gone.

**2. `GET /api/stations/{id}` — the registry, and the coordinates.** Ids run from
1 to roughly 148; beyond the end it 404s. Returns `code`, `district`, `type`,
`isActive`, `tankDepth`, `noOfPumps`, `waterLevelCM`, `lastSync`, `status`, a
`pumps[]` array of `{id, status, power, operatingHrs}` — and **real `latitude`
and `longitude`**.

There is no bulk station-list endpoint (`/api/stations` 404s), so the registry
costs one request per station. That is why it is a SEPARATE collector on a daily
cadence: 148 requests once a day is courteous, 148 requests every hour is not.
The cost of that choice is that pump running status is captured daily rather than
hourly, which is worth asking BMA to fix — a bulk endpoint would give us the
confounder at full resolution.

--------------------------------------------------------------------------
PERSONAL DATA — DROPPED, NOT COLLECTED
--------------------------------------------------------------------------
`/api/stations/{id}` also returns `contactPersonFirstName`,
`contactPersonLastName` and `phone` — named BMA staff and their phone numbers.
These are of no scientific value here and there is no reason to hold them. They
are dropped by name before anything is written, including from the raw payload,
and a test asserts they never reach the frame. This is the one place in the
package where the raw response is NOT stored verbatim, and the exception is
deliberate.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .base import http_get_json

HOST = "https://pumps.bangkok.go.th"
LEVELS_URL = f"{HOST}/api/water-levels"
STATION_URL = f"{HOST}/api/stations"

#: One hour is ~1,776 rows (148 stations x 12 five-minute readings). 2000 leaves
#: headroom for a late run without paginating.
DEFAULT_LIMIT = 2000

#: Ids observed to run 1..~148. We walk until this many consecutive 404s rather
#: than hard-coding a count that will drift the moment BMA installs a station.
MAX_STATION_ID = 400
STOP_AFTER_MISSES = 12

#: Never written to disk. See module docstring.
PII_FIELDS = ("contactPersonFirstName", "contactPersonLastName", "phone",
              "contactPerson", "contact_phone", "mobile")


def _strip_pii(obj: Any) -> Any:
    """Recursively remove personal fields from a payload before it is stored."""
    if isinstance(obj, dict):
        return {k: _strip_pii(v) for k, v in obj.items() if k not in PII_FIELDS}
    if isinstance(obj, list):
        return [_strip_pii(x) for x in obj]
    return obj


def district_prefix(code: Any) -> Any:
    """`PH.DDG.06` -> `DDG`, the token that joins to our station tables.

    Returns NA rather than guessing when the code is not in that shape — some
    stations use names like `dds-ratchada-02` instead. A wrong district is worse
    than a missing one: it would silently attach a pump reading to the wrong part
    of the city, and nothing downstream could detect that.
    """
    if not isinstance(code, str):
        return pd.NA
    parts = code.strip().split(".")
    if len(parts) >= 3 and parts[1]:
        return parts[1].upper()
    return pd.NA


# ---------------------------------------------------------------------------
# 1. Water levels — the hourly time series
# ---------------------------------------------------------------------------
def parse_levels(payload: Any) -> pd.DataFrame:
    records = (payload or {}).get("data") or []
    if not records:
        return pd.DataFrame()

    df = pd.json_normalize(records)

    # `nameEN` arrives as a nested object on some rows and a string on others,
    # so json_normalize produces either `nameEN` or `nameEN.*`. Neither is worth
    # depending on; the join key is `code`.
    rename = {"waterLevelCM": "water_level_cm",
              "waterLevelPercent": "water_level_pct",
              "stationId": "station_id",
              "code": "station_code",
              "nameTH": "name_th",
              "timestamp": "ts"}
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    for c in ("water_level_cm", "water_level_pct", "station_id"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"], errors="coerce")

    if "station_code" in df.columns:
        df["district_prefix"] = df["station_code"].map(district_prefix)

    return df


def fetch(limit: int = DEFAULT_LIMIT) -> Tuple[pd.DataFrame, Any]:
    """The hourly poll: one request, one hour of five-minute readings.

    Only `limit` is honoured — `pageSize`, `perPage`, `take` and `size` are
    accepted and silently ignored, returning the 20-row default. Do not
    'improve' this by switching parameter names without re-checking the row
    count that comes back.
    """
    payload = http_get_json(LEVELS_URL, params={"limit": int(limit)})
    return parse_levels(payload), payload


# ---------------------------------------------------------------------------
# 2. Station registry — daily, and the source of coordinates
# ---------------------------------------------------------------------------
def parse_station(payload: Any) -> Dict[str, Any]:
    """One station record, flattened, with pump status summarised and PII gone."""
    p = _strip_pii(payload or {})
    pumps = p.get("pumps") or []

    def _n(v: Any) -> Any:
        return pd.to_numeric(v, errors="coerce")

    running = [x for x in pumps
               if str(x.get("status", "")).lower() in ("on", "running", "active", "1", "true")]

    return {
        "station_id": p.get("id"),
        "station_code": p.get("code"),
        "district": p.get("district"),
        "name_th": p.get("nameTH"),
        "type": p.get("type"),
        "device_type": p.get("deviceType"),
        "is_active": p.get("isActive"),
        "lat": _n(p.get("latitude")),
        "long": _n(p.get("longitude")),
        "tank_depth": _n(p.get("tankDepth")),
        "n_pumps": _n(p.get("noOfPumps")),
        "n_pumps_running": len(running),
        "pump_statuses": ",".join(str(x.get("status")) for x in pumps),
        "pump_operating_hrs": ",".join(str(x.get("operatingHrs")) for x in pumps),
        "water_level_cm": _n(p.get("waterLevelCM")),
        "water_level_pct": _n(p.get("waterLevelPercent")),
        "last_sync": p.get("lastSync"),
        "status": p.get("status"),
        "cabinet_door_open": p.get("cabinetDoorOpen"),
    }


def fetch_stations(max_id: int = MAX_STATION_ID,
                   stop_after_misses: int = STOP_AFTER_MISSES
                   ) -> Tuple[pd.DataFrame, Any]:
    """Walk `/api/stations/{id}` until the ids run out.

    There is no bulk endpoint, so this is one request per station — about 148 of
    them. That is why this collector is daily and `fetch()` is hourly.
    """
    rows: List[Dict[str, Any]] = []
    raw: List[Any] = []
    misses = 0

    for sid in range(1, max_id + 1):
        try:
            payload = http_get_json(f"{STATION_URL}/{sid}", retries=1, timeout=20)
        except Exception:  # noqa: BLE001 — a 404 past the end is the stop signal
            misses += 1
            if misses >= stop_after_misses:
                break
            continue
        misses = 0
        raw.append(_strip_pii(payload))
        rows.append(parse_station(payload))

    if not rows:
        raise RuntimeError(
            f"no stations answered at {STATION_URL}/1..{max_id}. The API shape "
            "may have changed — re-check with the browser network tab."
        )

    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["last_sync"], errors="coerce")
    df["district_prefix"] = df["station_code"].map(district_prefix)
    return df, raw


def coordinates(df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """The columns worth keeping forever: code, district, position.

    Terrain contributes 0% of model gain today only because every station sits
    at a district centroid. These are measured positions for real BMA drainage
    infrastructure.
    """
    d = df if df is not None else fetch_stations()[0]
    out = d.loc[d["lat"].notna() & d["long"].notna(),
                ["station_code", "district_prefix", "district", "lat", "long",
                 "tank_depth", "n_pumps"]]
    return out.drop_duplicates("station_code").reset_index(drop=True)


SPEC = {
    "name": "pumps",
    "fetch": fetch,
    "time_col": "ts",
    "cadence_minutes": 60,
    "needs_permission": True,
    "provides": ["pump-station water level cm + % (5-min readings, ~148 stations)",
                 "district prefix PH.<DIST>.NN — joins to 27 of our 33 districts"],
    "verified": "2026-08-11 — schema read live in a browser; only `limit` is "
                "honoured, total 12.37M rows on a ~2-week rolling window. "
                "BLOCKED: Cloudflare returns 403 to HTTP clients — ask BMA",
}

STATIONS_SPEC = {
    "name": "pumps_stations",
    "fetch": fetch_stations,
    "time_col": "ts",
    "cadence_minutes": 1440,
    "needs_permission": True,
    "provides": ["REAL lat/long for ~148 BMA pump stations", "tank depth",
                 "pump count and per-pump status", "daily — no bulk endpoint exists"],
    "verified": "2026-08-11 — schema read live in a browser, ids 1..~148, "
                "coordinates confirmed inside Bangkok; PII fields dropped. "
                "BLOCKED: Cloudflare returns 403 to HTTP clients — ask BMA",
}
