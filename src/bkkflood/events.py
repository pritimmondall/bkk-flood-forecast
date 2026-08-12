"""
Turning a stream of depth readings into a list of flood events.

This is the most consequential definition in the project, so it is written once,
here, and its parameters live in config.yaml:

    A flood event at tier T is a period during which measured depth stays at or
    above T for at least two consecutive 5-minute readings. Separate excursions
    less than 60 minutes apart are merged into one event. Anything shorter than
    10 minutes is discarded as a spike.

Three questions people always ask:

*Why not simply depth > 0?*  Because 0.87% of all readings are non-zero but only
0.067% reach 5 cm. The gap is instrument noise — a device sitting on a wet road
reporting a few millimetres. A threshold has to sit above that noise floor.

*Why two consecutive readings?*  One 5-minute spike is a splash, a passing truck,
or a corrupted packet. Two removes most of that. Three or more starts discarding
genuine short flash floods, which are common here.

*Why merge at 60 minutes?*  Depth flickers around a threshold. Without merging,
one flooded afternoon becomes a dozen "events" and the count means nothing.

The work is split in two on purpose:

  `detect_excursions()`  — the expensive part. One SQL pass over 76 million rows
                           to find every unbroken run above the tier. Depends on
                           nothing but the tier.
  `assemble_events()`    — the cheap part. Applies the persistence, merge-gap and
                           minimum-duration rules in pandas.

That split is what makes the sensitivity analysis in notebook 02 affordable:
scan once, then re-apply the rules a hundred different ways for free.
"""

from __future__ import annotations

from typing import Iterable, List, Optional

import numpy as np
import pandas as pd

from .config import load_config
from .rawio import connect, interim_sql


# ---------------------------------------------------------------------------
# Step 1 — the expensive scan
# ---------------------------------------------------------------------------
def detect_excursions(
    tier_cm: float,
    years: Optional[Iterable[int]] = None,
    con=None,
) -> pd.DataFrame:
    """Every unbroken run of readings at or above `tier_cm`.

    No rules applied yet — a single 5-minute blip appears here as a one-reading
    excursion. Filtering is `assemble_events`'s job.

    Returns: station_code, started_at, ended_at, n_readings, peak_depth_cm.
    """
    cfg = load_config()
    cadence = cfg["data"]["cadence_minutes"]

    owns = con is None
    con = con or connect()
    try:
        src = interim_sql("flood", years)
        q = f"""
        WITH readings AS (
            -- NULL is not "dry". A missing reading tells us nothing, so it must
            -- break a run rather than silently continue or end one.
            SELECT station_code, ts, flood, (flood >= {tier_cm}) AS above
            FROM {src}
            WHERE flood IS NOT NULL
        ),
        marked AS (
            SELECT *,
                   lag(above) OVER w AS prev_above,
                   lag(ts)    OVER w AS prev_ts
            FROM readings
            WINDOW w AS (PARTITION BY station_code ORDER BY ts)
        ),
        grouped AS (
            -- A new excursion starts when we cross the tier from below, or when
            -- there is a hole in the record longer than one cadence step.
            SELECT *,
                   sum(CASE WHEN above AND (
                            prev_above IS NULL
                            OR NOT prev_above
                            OR date_diff('minute', prev_ts, ts) > {cadence}
                       ) THEN 1 ELSE 0 END) OVER (
                       PARTITION BY station_code ORDER BY ts
                   ) AS excursion_id
            FROM grouped_input
        )
        SELECT station_code,
               min(ts)          AS started_at,
               max(ts)          AS ended_at,
               count(*)::BIGINT AS n_readings,
               max(flood)       AS peak_depth_cm
        FROM grouped
        WHERE above
        GROUP BY station_code, excursion_id
        ORDER BY station_code, started_at
        """.replace("FROM grouped_input", "FROM marked")
        df = con.execute(q).fetchdf()
    finally:
        if owns:
            con.close()

    df["tier_cm"] = float(tier_cm)
    return df


# ---------------------------------------------------------------------------
# Step 2 — the cheap rules
# ---------------------------------------------------------------------------
def assemble_events(
    excursions: pd.DataFrame,
    persistence_readings: Optional[int] = None,
    merge_gap_minutes: Optional[int] = None,
    min_event_minutes: Optional[int] = None,
) -> pd.DataFrame:
    """Apply the three rules to raw excursions and return flood events.

    Defaults come from config.yaml. Override them only to *study* the definition
    (notebook 02), never to quietly use a different one.
    """
    cfg = load_config()
    ev = cfg["flood_event"]
    cadence = cfg["data"]["cadence_minutes"]
    persistence = persistence_readings or ev["persistence_readings"]
    gap = merge_gap_minutes if merge_gap_minutes is not None else ev["merge_gap_minutes"]
    min_minutes = (min_event_minutes if min_event_minutes is not None
                   else ev["min_event_minutes"])

    cols = ["station_code", "tier_cm", "started_at", "ended_at",
            "duration_minutes", "n_readings", "peak_depth_cm",
            "n_excursions_merged", "year"]
    if excursions.empty:
        return pd.DataFrame(columns=cols)

    # Rule 1 — persistence. A single reading is a splash, not a flood.
    df = excursions[excursions.n_readings >= persistence].copy()
    if df.empty:
        return pd.DataFrame(columns=cols)

    df = df.sort_values(["station_code", "started_at"]).reset_index(drop=True)
    df["started_at"] = pd.to_datetime(df["started_at"])
    df["ended_at"] = pd.to_datetime(df["ended_at"])

    # Rule 2 — merge excursions that are close together in the same place.
    prev_end = df.groupby("station_code")["ended_at"].shift()
    gap_min = (df["started_at"] - prev_end).dt.total_seconds() / 60
    new_event = prev_end.isna() | (gap_min > gap)
    df["event_id"] = new_event.groupby(df["station_code"]).cumsum()

    out = (df.groupby(["station_code", "event_id"], as_index=False)
             .agg(tier_cm=("tier_cm", "first"),
                  started_at=("started_at", "min"),
                  ended_at=("ended_at", "max"),
                  n_readings=("n_readings", "sum"),
                  peak_depth_cm=("peak_depth_cm", "max"),
                  n_excursions_merged=("n_readings", "size")))

    out["duration_minutes"] = (
        (out.ended_at - out.started_at).dt.total_seconds() / 60 + cadence
    ).astype(int)

    # Rule 3 — anything shorter than the minimum is a spike, not an event.
    out = out[out.duration_minutes >= min_minutes].copy()
    out["year"] = out.started_at.dt.year
    return (out[cols]
            .sort_values(["started_at", "station_code"])
            .reset_index(drop=True))


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------
def detect_events(
    tier_cm: Optional[float] = None,
    years: Optional[Iterable[int]] = None,
    con=None,
    **rule_overrides,
) -> pd.DataFrame:
    """Scan and apply the rules in one call. See the two functions above."""
    cfg = load_config()
    tier = tier_cm if tier_cm is not None else cfg["flood_event"]["primary_tier_cm"]
    return assemble_events(detect_excursions(tier, years, con=con), **rule_overrides)


def detect_events_all_tiers(
    years: Optional[Iterable[int]] = None, con=None
) -> pd.DataFrame:
    """Run the full detection for every tier in the config and stack the result."""
    tiers = sorted(load_config()["flood_event"]["tiers_cm"].values())
    owns = con is None
    con = con or connect()
    try:
        parts: List[pd.DataFrame] = [detect_events(t, years, con=con) for t in tiers]
    finally:
        if owns:
            con.close()
    return pd.concat(parts, ignore_index=True)


# ---------------------------------------------------------------------------
# Row-level class balance
# ---------------------------------------------------------------------------
def class_balance(years: Optional[Iterable[int]] = None, con=None) -> pd.DataFrame:
    """How rare is a flood, per year, per tier — measured, not quoted.

    This is the number that decides the whole modelling strategy, which is why
    it is computed from the data every time rather than carried in a document.
    """
    cfg = load_config()
    tiers = sorted(cfg["flood_event"]["tiers_cm"].values())
    owns = con is None
    con = con or connect()
    try:
        src = interim_sql("flood", years)
        tier_cols = ", ".join(
            f"sum(CASE WHEN flood >= {t} THEN 1 ELSE 0 END)::BIGINT AS n_ge{int(t)}"
            for t in tiers
        )
        q = f"""
            SELECT year(ts)::INT                                          AS year,
                   count(*)::BIGINT                                       AS rows,
                   count(flood)::BIGINT                                   AS rows_with_value,
                   sum(CASE WHEN flood IS NULL THEN 1 ELSE 0 END)::BIGINT AS rows_null,
                   sum(CASE WHEN flood = 0 THEN 1 ELSE 0 END)::BIGINT     AS rows_zero,
                   sum(CASE WHEN flood > 0 THEN 1 ELSE 0 END)::BIGINT     AS n_gt0,
                   {tier_cols},
                   max(flood)                                             AS max_depth_cm
            FROM {src}
            GROUP BY 1 ORDER BY 1
        """
        df = con.execute(q).fetchdf()
    finally:
        if owns:
            con.close()

    for t in tiers:
        t = int(t)
        df[f"pct_ge{t}"] = (100 * df[f"n_ge{t}"] / df["rows"]).round(5)
        df[f"one_in_ge{t}"] = (df["rows"] / df[f"n_ge{t}"]).round(0)
    return df
