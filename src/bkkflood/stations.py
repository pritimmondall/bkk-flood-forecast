"""
Station codes, district prefixes, and the honest state of our coordinates.

Every station code looks like TYPE.PREFIX.NN — for example FL.BBN.01.

For **rain** and **flood** sensors the middle part is a district abbreviation
(BBN = Bang Bon), which is why rainfall can be joined to flood sites by
district. For **water** and **flow** sensors the middle part is a *canal* name
abbreviation (SSB = Saen Saep), which is a different naming system entirely.
WL.STN.01 is a canal, not Sathon district.

That single fact is why canal water level and flow currently enter the model as
citywide averages instead of local inputs, and it is fixed by a spreadsheet of
coordinates rather than by any amount of modelling.
"""

from __future__ import annotations

from typing import Dict, Iterable, Optional, Set

import pandas as pd

from .config import load_config, resolve


def district_prefix(station_code: str) -> Optional[str]:
    """Pull the middle segment out of a station code.

    >>> district_prefix("FL.BBN.01")
    'BBN'
    """
    parts = str(station_code).split(".")
    return parts[1] if len(parts) >= 2 else None


def prefixes(codes: Iterable[str]) -> Set[str]:
    """The set of distinct prefixes in a collection of station codes."""
    return {p for p in (district_prefix(c) for c in codes) if p}


def prefix_coverage(flood_codes: Iterable[str], other_codes: Iterable[str]) -> Dict:
    """How much of the flood-sensor network another dataset can reach by code.

    Returns the covered count, the total, the percentage, and the list of flood
    districts the other dataset cannot reach — which is the actionable half.
    """
    flood_p, other_p = prefixes(flood_codes), prefixes(other_codes)
    covered = flood_p & other_p
    return {
        "flood_prefixes": len(flood_p),
        "covered": len(covered),
        "pct": round(100 * len(covered) / len(flood_p), 1) if flood_p else 0.0,
        "uncovered": sorted(flood_p - other_p),
    }


def load_registry() -> pd.DataFrame:
    """Load data/station_registry_full.csv, with its caveats attached.

    WARNING, and this matters every time the registry is used: these are not
    surveyed sensor positions. They were *inferred* in an earlier version of
    the project — "High" confidence means a district centroid derived from a
    shared code prefix, so every flood sensor in Bang Bon carries the identical
    coordinate and they stack on top of each other on a map.

    Good enough for a district choropleth. Not good enough for distance
    features, spatial interpolation, or a flood surface. The added
    `coord_quality` column is what the API must expose so the frontend can show
    a dashed marker rather than pretend.
    """
    cfg = load_config()
    path = resolve(cfg["paths"]["station_registry"])
    df = pd.read_csv(path, encoding="utf-8-sig")

    def quality(row) -> str:
        # Order matters. The district-centroid basis text *mentions* subdistricts
        # ("mean of subdistrict coords"), so check for it first or everything
        # gets misclassified as the more precise of the two.
        if pd.isna(row.get("lat")):
            return "none"
        basis = str(row.get("basis", "")).lower()
        if "district centroid" in basis:
            return "district_centroid"
        if "subdistrict" in basis and "centroid" in basis:
            return "subdistrict_centroid"
        return "inferred_other"

    df["coord_quality"] = df.apply(quality, axis=1)
    df["has_coords"] = df["lat"].notna()
    return df


def registry_summary(df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Sensor type x coordinate quality, so the caveat is impossible to miss."""
    df = load_registry() if df is None else df
    return (
        df.groupby(["sensor_type", "coord_quality"])
        .size()
        .rename("stations")
        .reset_index()
        .sort_values(["sensor_type", "coord_quality"])
        .reset_index(drop=True)
    )
