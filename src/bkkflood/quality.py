"""
Measuring how good the data actually is, one station-year at a time.

The point of this module is a single table — the quality scorecard — that
answers, for every sensor in every year: how many readings should there have
been, how many are actually present, how many are missing, and what range the
values covered.

Why it matters more than it sounds: across this archive the share of missing
flood readings rises from 0% in 2019 to 10.7% in 2025. If a model cannot tell
"the road was dry" from "the sensor was offline", it will learn the wrong
lesson from the years we test it on.
"""

from __future__ import annotations

from typing import Iterable, List, Optional

import pandas as pd

from .config import load_config
from .rawio import connect, interim_sql


def _expected_rows(year: int, cadence_minutes: int) -> int:
    """How many readings a perfectly healthy sensor produces in one year."""
    days = 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365
    return days * 24 * 60 // cadence_minutes


def station_year_profile(
    dataset: str,
    years: Optional[Iterable[int]] = None,
    con=None,
) -> pd.DataFrame:
    """One row per station per year: counts, coverage, and value ranges.

    Reads the cleaned Parquet (notebook 01 must have run). Streams — it never
    loads a whole year into memory.
    """
    cfg = load_config()
    schema = cfg["data"]["schema"][dataset]
    years = list(years or cfg["data"]["years"])

    owns = con is None
    con = con or connect()
    try:
        frames: List[pd.DataFrame] = []
        for year in years:
            src = interim_sql(dataset, [year])
            aggs = []
            for col in schema["values"]:
                aggs += [
                    f"count({col})::BIGINT AS n_{col}",
                    f"min({col}) AS min_{col}",
                    f"max({col}) AS max_{col}",
                    f"avg({col}) AS mean_{col}",
                ]
            extra = ""
            if dataset == "flood":
                tiers = cfg["flood_event"]["tiers_cm"]
                extra = ", " + ", ".join(
                    f"sum(CASE WHEN flood >= {cm} THEN 1 ELSE 0 END)::BIGINT AS n_ge{cm}"
                    for cm in sorted(tiers.values())
                ) + ", sum(CASE WHEN flood > 0 THEN 1 ELSE 0 END)::BIGINT AS n_gt0"

            q = f"""
                SELECT station_code,
                       any_value(station_name)      AS station_name,
                       count(*)::BIGINT             AS rows,
                       count(DISTINCT ts)::BIGINT   AS n_timestamps,
                       min(ts) AS ts_min, max(ts) AS ts_max,
                       {', '.join(aggs)}{extra}
                FROM {src}
                GROUP BY station_code
                ORDER BY station_code
            """
            df = con.execute(q).fetchdf()
            df.insert(0, "year", year)
            df.insert(0, "dataset", dataset)
            frames.append(df)

        out = pd.concat(frames, ignore_index=True)
    finally:
        if owns:
            con.close()

    cadence = cfg["data"]["cadence_minutes"]
    out["expected_rows"] = out["year"].map(lambda y: _expected_rows(y, cadence))
    out["row_completeness_pct"] = (100 * out["rows"] / out["expected_rows"]).round(3)
    out["duplicate_timestamps"] = out["rows"] - out["n_timestamps"]

    # "Primary" column = the one that carries the meaning of the dataset.
    primary = {"flood": "flood", "rain": "rf1hr", "water": "wl_in", "flow": "flow"}[dataset]
    out["primary_column"] = primary
    out["null_pct"] = (100 * (1 - out[f"n_{primary}"] / out["rows"])).round(3)
    out["sensor_effectively_offline"] = out["null_pct"] > 50
    return out


def quality_scorecard(
    datasets: Optional[Iterable[str]] = None,
    years: Optional[Iterable[int]] = None,
    con=None,
) -> pd.DataFrame:
    """Stack the per-dataset profiles into one scorecard.

    Only the columns common to all four datasets are kept, so the result is a
    single tidy table you can group by dataset, year or station.
    """
    from .rawio import DATASETS

    keep = [
        "dataset", "year", "station_code", "station_name",
        "rows", "expected_rows", "row_completeness_pct",
        "n_timestamps", "duplicate_timestamps",
        "ts_min", "ts_max",
        "primary_column", "null_pct", "sensor_effectively_offline",
    ]
    owns = con is None
    con = con or connect()
    try:
        parts = [
            station_year_profile(ds, years, con=con)[keep]
            for ds in (datasets or DATASETS)
        ]
    finally:
        if owns:
            con.close()
    return pd.concat(parts, ignore_index=True)
