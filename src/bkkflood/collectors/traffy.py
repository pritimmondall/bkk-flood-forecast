"""
Traffy Fondue — citizen flood reports.

--------------------------------------------------------------------------
THIS IS NOT A MODEL INPUT
--------------------------------------------------------------------------
A citizen reports a flood after standing in it. By the time a report exists the
thing we were trying to forecast has already happened, so feeding this to the
model as a feature would leak the label and produce a beautiful, useless score.

Its real value is the one question nobody in this project can currently answer:
**how much flooding does the 107-sensor network miss?** Every label we have comes
from a BMA sensor. If a road floods where there is no sensor, it did not happen
as far as the model and the evaluation are concerned. Traffy reports are
independent of our instrumentation, so they are the first outside check on the
ground truth — `data_requests.md` Priority 7, obtainable today for free.

Collect it into `data/live/traffy/`, keep it out of `features.py`, and use it in
evaluation only.

--------------------------------------------------------------------------
SCHEMA VERIFIED 2026-08-10 — AND THE FIRST DRAFT WAS WRONG
--------------------------------------------------------------------------
The real `properties` object was read from the live endpoint. The field carrying
the citizen's text is **`description`**, not `comment`. The first version of this
parser looked for `comment`, found nothing, and would have marked every English
report `is_flood = False` while still writing plausible-looking rows — a silent
failure that only shows up months later as "why does Traffy think Bangkok never
floods".

Confirmed field list (33 properties): problem_type_fondue, org, org_action,
description, message_id, ticket_id, photo_url, after_photo, address, subdistrict,
district, province, problem_type_abdul, star, count_reopen, note,
description_reporter, state, state_type_latest, duration_minutes_inprogress,
duration_minutes_finished, duration_minutes_total, view_count, timestamp,
last_activity, timestamp_inprogress, timestamp_finished, ai, type, see_info,
problemtype_photo, total_point, like, dislike.

Because being wrong once is evidence of being wrong again, every original
property is also kept as a `raw_*` column. A future field rename costs a
rewrite of `_pick`, not a season of reports.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .base import http_get_json

ENDPOINT = "https://publicapi.traffy.in.th/teamchadchart-stat-api/geojson/v1"

#: Thai for "flooding" — Traffy's own category tag, and the string that actually
#: appears in `problem_type_fondue` / `type`.
FLOOD_TAG = "น้ำท่วม"

#: Other Thai phrases that mean standing water without using the tag above.
#: Kept explicit rather than clever: this list is auditable, a regex is not.
FLOOD_PHRASES = ("น้ำท่วม", "น้ำขัง", "น้ำรอระบาย", "ท่วมขัง")

#: Our stable name -> the property keys it may arrive under.
ALIASES: Dict[str, List[str]] = {
    "ticket_id": ["ticket_id", "message_id", "id"],
    "ts": ["timestamp", "last_activity"],
    "ts_last_activity": ["last_activity"],
    "state": ["state"],
    "state_latest": ["state_type_latest"],
    "types": ["problem_type_fondue", "type", "problem_type_abdul"],
    "type_abdul": ["problem_type_abdul"],
    "description": ["description", "description_reporter", "comment", "note"],
    "address": ["address"],
    "district": ["district"],
    "subdistrict": ["subdistrict"],
    "province": ["province"],
    "org": ["org"],
    "photo_url": ["photo_url"],
    "after_photo": ["after_photo"],
    "view_count": ["view_count"],
    "duration_minutes_total": ["duration_minutes_total"],
}


def _as_text(v: Any) -> str:
    """Flatten whatever a property holds into searchable text.

    `problem_type_fondue` and `type` are lists; `description` is a string;
    `ai` is a dict. All three have to end up as something `.str.contains` can
    look at, and `str(list)` is good enough for a substring search.
    """
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v if x is not None)
    return str(v)


def _pick(props: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    lowered = {str(k).lower(): k for k in props}
    for target, cands in ALIASES.items():
        val = None
        for cand in cands:
            key = lowered.get(cand.lower())
            if key is not None and props.get(key) not in (None, "", []):
                val = props[key]
                break
        out[target] = _as_text(val) if isinstance(val, (list, tuple)) else val
    return out


def parse(payload: Any, bangkok_only: bool = True) -> pd.DataFrame:
    """GeoJSON -> tidy frame. Separated from `fetch` so it is testable offline."""
    feats = (payload or {}).get("features") or []
    if not feats:
        return pd.DataFrame()

    rows: List[Dict[str, Any]] = []
    for f in feats:
        props = f.get("properties") or {}
        geom = f.get("geometry") or {}
        coords = geom.get("coordinates") or []

        row = _pick(props)
        # GeoJSON is [longitude, latitude]. Swapping them puts Bangkok in the
        # Indian Ocean, so the order is asserted in the tests as well.
        row["long"] = coords[0] if len(coords) > 0 else None
        row["lat"] = coords[1] if len(coords) > 1 else None

        # Everything we did not map, kept verbatim. See module docstring.
        for k, v in props.items():
            key = f"raw_{k}"
            if key not in row:
                row[key] = _as_text(v) if isinstance(v, (list, tuple, dict)) else v
        rows.append(row)

    df = pd.DataFrame(rows)

    df["ts"] = pd.to_datetime(df["ts"], errors="coerce", utc=True).dt.tz_localize(None)
    if "ts_last_activity" in df.columns:
        df["ts_last_activity"] = pd.to_datetime(
            df["ts_last_activity"], errors="coerce", utc=True
        ).dt.tz_localize(None)
    for c in ("lat", "long", "view_count", "duration_minutes_total"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    blob = (
        df.get("types", pd.Series("", index=df.index)).fillna("").astype(str)
        + " "
        + df.get("type_abdul", pd.Series("", index=df.index)).fillna("").astype(str)
        + " "
        + df.get("description", pd.Series("", index=df.index)).fillna("").astype(str)
    )
    thai = blob.str.contains("|".join(FLOOD_PHRASES), regex=True, na=False)
    eng = blob.str.lower().str.contains("flood", na=False)
    df["is_flood"] = thai | eng

    if bangkok_only:
        df = _bangkok_only(df)

    return df.reset_index(drop=True)


def _bangkok_only(df: pd.DataFrame) -> pd.DataFrame:
    """Drop reports from outside Bangkok. The feed is national.

    The guard is on whether `province` is POPULATED, not on whether any row
    matches Bangkok. An earlier version asked "did anything match?" and skipped
    filtering when nothing did — which meant a response containing only
    upcountry reports was passed through whole. A Phrae flood entering the
    coverage check would make our sensor network look worse than it is, in a way
    that is invisible once the rows are in the parquet.

    When `province` is genuinely absent we fall back to a Bangkok bounding box
    rather than trusting the whole feed.
    """
    if "province" in df.columns:
        prov = df["province"].fillna("").astype(str).str.strip()
        if (prov != "").any():
            return df[prov.str.contains("กรุงเทพ|Bangkok", regex=True, na=False)]

    if {"lat", "long"} <= set(df.columns):
        return df[df["lat"].between(13.4, 14.1) & df["long"].between(100.2, 100.95)]

    return df


def fetch(limit: Optional[int] = 2000,
          bangkok_only: bool = True) -> Tuple[pd.DataFrame, Any]:
    """Poll the feed.

    `limit` exists because the feed is national and unbounded. 2000 covers a
    normal day's Bangkok reports many times over; without it a heavy rain day
    nationally would pull tens of megabytes every hour for rows we discard.
    """
    params: Dict[str, Any] = {}
    if limit:
        params["limit"] = int(limit)
    payload = http_get_json(ENDPOINT, params=params or None)
    return parse(payload, bangkok_only=bangkok_only), payload


SPEC = {
    "name": "traffy",
    "fetch": fetch,
    "time_col": "ts",
    "cadence_minutes": 60,
    "needs_permission": False,
    "provides": ["citizen flood reports with point coordinates — EVALUATION ONLY"],
    "verified": "2026-08-10 — GeoJSON read live, 33 properties confirmed, "
                "text field is `description` not `comment`",
}
