"""
BMA Department of Drainage and Sewerage — rain, canal level, flow.

--------------------------------------------------------------------------
THIS IS THE ONE THAT MATTERS, AND IT IS OFF BY DEFAULT
--------------------------------------------------------------------------
`weather.bangkok.go.th` publishes, as numbers, the three networks the model
trains on: 24-hour accumulated rainfall, canal water level inside and outside
the gate, and flow rate in m3/s. The units on the page are `ม.รทก.` — metres
above MSL — which also answers the datum question left open in
`data_requests.md` Priority 2.

A REST endpoint on that host is search-indexed:

    http://weather.bangkok.go.th/dds_webservices/api/rain/lastdata

**Its response body has never been read by us, and the host now looks
internal-only or dead.** The evidence, in order:

- 2026-08-10, WebFetch: refused — `robots.txt fetch failed: ConnectTimeout`.
  It could not even load the robots file.
- 2026-08-11, **Chrome on a residential connection in Bangkok**:
  `ERR_CONNECTION_RESET`. Not a 403, not a 404, not a timeout — the connection
  is actively reset.

That last one is the informative result. A browser inside Thailand cannot reach
the host at all, which rules out geoblocking as the explanation and points at
one of: the service is firewalled to BMA's internal network, it has been
decommissioned, or it is simply down. A public page that search engines indexed
at some point is no longer publicly served.

So the question for BMA is no longer "may we have documented access to this
endpoint". It is **"is this host still running, and is it internal-only?"** —
and if the answer is that it moved or was retired, what replaced it. Every field
name below remains a GUESS, and `parse()` is written to survive being wrong.

--------------------------------------------------------------------------
WHY `ENABLED = False`
--------------------------------------------------------------------------
Project rule 8: this is a government system and the project's entire purpose is
a BMA partnership. Discovering an undocumented endpoint is not the same as being
allowed to poll it hourly forever. `probe()` makes ONE request per candidate
path so you can see what exists and put a concrete question to BMA. Scheduled
collection stays off until someone answers that question in writing.

Turning this on before asking is a bad trade: it risks the relationship that the
whole project depends on, to gain data BMA would very likely hand over if asked.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pandas as pd

from .base import http_get_json

HOST = "http://weather.bangkok.go.th"
BASE = f"{HOST}/dds_webservices/api"

#: Flip to True only after BMA has said yes. See module docstring.
ENABLED = False

#: The one path we have actual evidence for, plus the obvious siblings.
#: `probe()` reports which of these respond; it does not assume any of them do.
CANDIDATES: Dict[str, str] = {
    "rain": f"{BASE}/rain/lastdata",
    "waterlevel": f"{BASE}/waterlevel/lastdata",
    "water": f"{BASE}/water/lastdata",
    "flow": f"{BASE}/flow/lastdata",
    "pump": f"{BASE}/pump/lastdata",
    "index": f"{BASE}/",
}

#: Column aliases, keyed by our name. Every one of these is a guess about an
#: undocumented API; `_pick` falls back to NA rather than raising when a guess
#: is wrong, so a schema surprise costs us a column and not the whole poll.
ALIASES: Dict[str, List[str]] = {
    "station_code": ["code", "station_code", "rain_code", "water_code", "flow_code",
                     "stationid", "station_id", "id"],
    "station_name": ["name", "station_name", "rain_name", "water_name", "flow_name"],
    "ts": ["datetime", "site_timestamp", "timestamp", "date_time", "lastupdate",
           "last_update", "updatetime"],
    "lat": ["lat", "latitude", "y"],
    "long": ["long", "lng", "longitude", "x"],
    "district": ["district", "amphoe", "area", "zone"],
    # rainfall accumulations, matching the training CSV columns exactly
    "rf5min": ["rf5min", "rain5min"],
    "rf15min": ["rf15min", "rain15min"],
    "rf30min": ["rf30min", "rain30min"],
    "rf1hr": ["rf1hr", "rain1hr", "rain_1h"],
    "rf3hr": ["rf3hr", "rain3hr"],
    "rf6hr": ["rf6hr", "rain6hr"],
    "rf12hr": ["rf12hr", "rain12hr"],
    "rf24hr": ["rf24hr", "rain24hr", "rain_24h", "rainfall24"],
    # canal level / flow
    "wl_in": ["wl_in", "waterlevel_in", "inside", "level_in"],
    "wl_out01": ["wl_out01", "wl_out", "waterlevel_out", "outside", "level_out"],
    "flow": ["flow", "flowrate", "flow_rate", "discharge"],
    "mean_velocity": ["mean_velocity", "velocity"],
    "area": ["area_m2", "section_area"],
}


def _find_records(payload: Any) -> List[Dict[str, Any]]:
    """Longest list-of-dicts anywhere in the payload. See thaiwater._find_records."""
    best: List[Dict[str, Any]] = []

    def walk(node: Any) -> None:
        nonlocal best
        if isinstance(node, list):
            if node and all(isinstance(x, dict) for x in node) and len(node) > len(best):
                best = node
            for x in node:
                walk(x)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)

    walk(payload)
    return best


def _pick(flat: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=flat.index)
    lowered = {c.lower(): c for c in flat.columns}
    for target, cands in ALIASES.items():
        found = None
        for cand in cands:
            if cand.lower() in lowered:
                found = lowered[cand.lower()]
                break
        if found is None:
            for cand in cands:
                for low, orig in lowered.items():
                    if low.endswith("." + cand.lower()):
                        found = orig
                        break
                if found:
                    break
        out[target] = flat[found] if found is not None else pd.NA
    return out


def parse(payload: Any, kind: str) -> pd.DataFrame:
    records = _find_records(payload)
    if not records:
        return pd.DataFrame()

    flat = pd.json_normalize(records)
    df = _pick(flat)
    df["kind"] = kind

    df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
    numeric = [c for c in df.columns
               if c.startswith(("rf", "wl_")) or c in
               ("flow", "mean_velocity", "area", "lat", "long")]
    for c in numeric:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Keep every original column too. When the guesses above turn out wrong, the
    # data is still here and re-parsing costs a function, not a season.
    for c in flat.columns:
        key = f"raw_{c}"
        if key not in df.columns:
            df[key] = flat[c]
    return df


def probe(candidates: Dict[str, str] | None = None) -> pd.DataFrame:
    """One request per candidate path. Discovery, not collection.

    Returns a frame describing what answered: status, whether it parsed as JSON,
    how many records, and the field names found. That table is the attachment
    for the email to BMA.
    """
    cands = candidates or CANDIDATES
    rows: List[Dict[str, Any]] = []
    for kind, url in cands.items():
        row: Dict[str, Any] = {"kind": kind, "url": url}
        try:
            payload = http_get_json(url, retries=1, timeout=20)
            recs = _find_records(payload)
            row.update(
                ok=True,
                n_records=len(recs),
                fields=", ".join(sorted(recs[0].keys()))[:400] if recs else "",
                error="",
            )
        except Exception as exc:  # noqa: BLE001
            row.update(ok=False, n_records=0, fields="", error=str(exc)[:200])
        rows.append(row)
    return pd.DataFrame(rows)


def fetch(kinds: tuple = ("rain", "waterlevel", "flow")) -> Tuple[pd.DataFrame, Any]:
    if not ENABLED:
        raise RuntimeError(
            "bma_dds is disabled. This is a BMA government system and project "
            "rule 8 requires permission before automated collection. Run "
            "probe() for discovery, ask BMA, then set ENABLED = True."
        )
    frames: List[pd.DataFrame] = []
    raw: Dict[str, Any] = {}
    for kind in kinds:
        url = CANDIDATES.get(kind)
        if not url:
            continue
        payload = http_get_json(url)
        raw[kind] = payload
        frames.append(parse(payload, kind))
    if not frames:
        return pd.DataFrame(), raw
    return pd.concat(frames, ignore_index=True), raw


SPEC = {
    "name": "bma_dds",
    "fetch": fetch,
    "time_col": "ts",
    "cadence_minutes": 15,
    "needs_permission": True,
    "provides": ["BMA rain gauges", "canal level in/out (MSL)", "flow m3/s"],
    "verified": "NOT VERIFIED — endpoint indexed, body never read. See docstring.",
}
