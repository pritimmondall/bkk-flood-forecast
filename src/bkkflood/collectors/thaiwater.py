"""
ThaiWater (HII / Royal Irrigation Department) — Bangkok canal water levels.

--------------------------------------------------------------------------
WHY THIS COLLECTOR IS FIRST
--------------------------------------------------------------------------
It is the only source verified working with no permission needed, and it is the
only one that hands us REAL COORDINATES. Phase 5 established that terrain
contributes 0% of model gain because every station sits at a district centroid.
`tele_station_lat/long` here are genuine positions — the first real positional
data the project has held.

It also carries a Chao Phraya river gauge. We currently reconstruct tidal
*phase* from lunar periods and have no amplitude at all; a measured river level
is the thing that proxy was standing in for.

Verified 2026-08-10: 11 Bangkok stations, hourly, timestamped 16:00 the same
afternoon, no authentication.

--------------------------------------------------------------------------
THE HONEST LIMITS
--------------------------------------------------------------------------
Eleven stations against the 300 in our training data — a far sparser network.
Hourly, not 5-minute. And measured on its own (feature set E), canal level plus
GFS reaches 4.9% event POD against replay's 53%. Canal level is a MULTIPLIER ON
RAIN, not a replacement for it: given rainfall it sharpens the picture
considerably; without rainfall there is nothing for it to sharpen.

Collect it anyway. Every day this does not run is real data at real coordinates
gone permanently, and the day a rain feed opens this is already accumulating.

--------------------------------------------------------------------------
THREE THINGS THE FIRST REAL COLLECTION EXPOSED (2026-08-11)
--------------------------------------------------------------------------
**1. `waterlevel_datetime` is Asia/Bangkok local time, not UTC, and it arrives
with no timezone marker.** Proved arithmetically: the newest reading in a poll
made at 05:19 UTC was stamped 12:00. Read as UTC that is nearly seven hours in
the future; read as UTC+7 it is nineteen minutes old.

This is the most dangerous thing in the file. Everything else in this project is
UTC, `_fetched_at_utc` is UTC, and a naive join would place every canal reading
seven hours away from the rainfall that caused it. It would not error. It would
simply destroy the correlation, and the conclusion would be "canal levels do not
predict floods" — which is the opposite of what Phase 5 measured. So `ts` is
converted to UTC here, at the boundary, and `ts_local` is kept beside it.

**2. Two of the eleven stations have no English name.** They are `NaN`, not
empty strings, so any `groupby("station_name")` silently drops them — which is
exactly what happened to the first coordinates export: 9 stations written out of
11. Grouping is by `station_id`; `station_label` exists for display and always
has a value.

**3. One station's bank reference is zero, and that makes it read as flooding.**
Station 11688984 reports `min_bank = 0.00`, so `diff_wl_bank` comes back 0.00 and
`diff_wl_bank_text` reads `เท่าระดับตลิ่ง` — *water at bank level*. Every other
station has `min_bank` between 0.62 and 4.46 m. It is a missing reference value
formatted as a maximum-severity reading, and any alerting rule keyed on bank
clearance would fire on it forever.

It is flagged, not deleted. `bank_ref_valid` marks it and `diff_wl_bank_clean`
is NaN where the reference is unusable, while `diff_wl_bank` keeps whatever the
API said. Phase 0 taught this the hard way: a validity check that quietly edits
the data destroys the evidence you would need to understand it later.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .base import http_get_json, utc_now

ENDPOINT = "https://api-v3.thaiwater.net/api/v1/thaiwater30/provinces/waterlevel"
BANGKOK_PROVINCE_CODE = 10

#: Columns we care about, mapped from whatever the API calls them.
#: Matched on the *suffix* of the flattened (dotted) column name, because the
#: nesting depth is not documented and has no reason to stay stable.
ALIASES: Dict[str, List[str]] = {
    "ts": ["waterlevel_datetime"],
    "station_id": ["station.id", "id"],
    "station_name": ["station.tele_station_name.en", "station.tele_station_name.th"],
    "lat": ["tele_station_lat", "station.tele_station_lat", "lat"],
    "long": ["tele_station_long", "station.tele_station_long", "long"],
    "waterlevel_m": ["waterlevel_m"],
    "waterlevel_msl": ["waterlevel_msl"],
    "waterlevel_msl_previous": ["waterlevel_msl_previous"],
    "flow_rate": ["flow_rate"],
    "discharge": ["discharge"],
    "storage_percent": ["storage_percent"],
    "situation_level": ["situation_level"],
    "station_type": ["station_type"],
    "diff_wl_bank": ["diff_wl_bank"],
    "diff_wl_bank_text": ["diff_wl_bank_text"],
    "ground_level": ["station.ground_level", "ground_level"],
    "left_bank": ["station.left_bank", "left_bank"],
    "right_bank": ["station.right_bank", "right_bank"],
    "min_bank": ["station.min_bank", "min_bank"],
    "river_name": ["river_name"],
    "basin_name": ["basin.basin_name.en", "basin.basin_name.th", "basin.name"],
    "district": ["geocode.amphoe_name.en", "amphoe_name.en"],
    "subdistrict": ["geocode.tumbon_name.en", "tumbon_name.en"],
    "province": ["geocode.province_name.en", "province_name.en"],
    "agency": ["agency.agency_shortname.en", "agency.agency_name.en"],
}

#: Verified 2026-08-10 by reading the live response. If the API stops returning
#: roughly this many Bangkok stations, something changed upstream and the parser
#: should be re-checked rather than trusted.
EXPECTED_STATIONS = 11


def _find_records(payload: Any) -> List[Dict[str, Any]]:
    """Locate the station list without assuming the envelope shape.

    The response has been seen as `{"data": [...]}`, but a wrapper key changing
    is exactly the kind of silent break that would leave us collecting empty
    files for a month. So: take the longest list of dicts anywhere in the
    payload, and let the caller assert on the count.
    """
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


def _pick(df: pd.DataFrame) -> pd.DataFrame:
    """Rename the flattened frame down to our stable column names."""
    out = pd.DataFrame(index=df.index)
    lowered = {c.lower(): c for c in df.columns}

    for target, candidates in ALIASES.items():
        found = None
        for cand in candidates:
            if cand.lower() in lowered:
                found = lowered[cand.lower()]
                break
        if found is None:
            # Suffix match: "station.tele_station_lat" also satisfies "tele_station_lat"
            for cand in candidates:
                for low, orig in lowered.items():
                    if low.endswith("." + cand.lower()) or low == cand.lower():
                        found = orig
                        break
                if found:
                    break
        out[target] = df[found] if found is not None else pd.NA
    return out


#: ThaiWater stamps readings in Thai local time with no offset. See docstring.
SOURCE_TZ_OFFSET_HOURS = 7


def parse(payload: Any, now: Optional[datetime] = None) -> pd.DataFrame:
    """Payload -> tidy frame. Separated from `fetch` so it is testable offline."""
    records = _find_records(payload)
    if not records:
        return pd.DataFrame()

    flat = pd.json_normalize(records)
    df = _pick(flat)

    # --- time: convert at the boundary, keep the original beside it ----------
    df["ts_local"] = pd.to_datetime(df["ts"], errors="coerce")
    df["ts"] = df["ts_local"] - pd.Timedelta(hours=SOURCE_TZ_OFFSET_HOURS)
    stamp = pd.Timestamp(now or utc_now()).tz_localize(None)
    df["age_minutes"] = ((stamp - df["ts"]).dt.total_seconds() / 60).round(1)

    for c in ("lat", "long", "waterlevel_m", "waterlevel_msl",
              "waterlevel_msl_previous", "flow_rate", "discharge",
              "storage_percent", "diff_wl_bank", "ground_level",
              "left_bank", "right_bank", "min_bank"):
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # --- a label that always exists -----------------------------------------
    # Two of eleven stations return `station_name` as null. Grouping on it drops
    # them without a word, which is how the first coordinates export lost two
    # stations. Group on `station_id`; display `station_label`.
    df["station_label"] = (
        df["station_name"].astype("object")
        .fillna(df["river_name"].astype("object"))
        .fillna(df["subdistrict"].astype("object"))
        .fillna("station_" + df["station_id"].astype(str))
    )

    # --- bank clearance: flag the unusable reference, do not erase it --------
    df["bank_ref_valid"] = df["min_bank"].notna() & (df["min_bank"] > 0)
    df["diff_wl_bank_clean"] = df["diff_wl_bank"].where(df["bank_ref_valid"])

    # The rise signal the model actually uses. Computed here rather than in
    # features.py because `_previous` is only meaningful next to the reading it
    # came with — once these are two rows in a table the pairing is lost.
    df["wl_rise_m"] = df["waterlevel_msl"] - df["waterlevel_msl_previous"]

    # NOT imputed. A station that is offline stays NaN. LightGBM handles NaN
    # natively; an invented canal level is worse than a missing one because the
    # model cannot tell it was invented.
    return df.sort_values("ts").reset_index(drop=True)


def fetch(province_code: int = BANGKOK_PROVINCE_CODE) -> Tuple[pd.DataFrame, Any]:
    payload = http_get_json(ENDPOINT, params={"province_code": province_code})
    return parse(payload), payload


#: What the runner needs to know about this source.
SPEC = {
    "name": "thaiwater",
    "fetch": fetch,
    "time_col": "ts",
    "cadence_minutes": 60,
    "needs_permission": False,
    "provides": ["canal water level (MSL)", "rise", "flow rate", "coordinates",
                 "Chao Phraya river level", "bank clearance"],
    "verified": "2026-08-11 — 11 Bangkok stations collected live. Timestamps are "
                "Asia/Bangkok (converted to UTC here); 2 stations have null "
                "names; station 11688984 has min_bank=0 and reads as at-bank",
}
