"""
Turning flood depth into something a model can be trained against.

--------------------------------------------------------------------------
THE TWO RULES THAT MATTER
--------------------------------------------------------------------------
**1. Labels come from the 5-minute data, features from the 15-minute grid.**

The model runs every 15 minutes because neighbouring 5-minute rows are so
similar that the extra rows triple the size of everything without adding
information. But the median flood event at 15 cm lasts 45 minutes and a quarter
of them are under 25 minutes, so a label built by sampling every 15 minutes
would miss events entirely. Labels therefore take the **maximum depth over the
full 5-minute record** inside the forward window. Nothing is missed; nothing is
inflated.

**2. A feature may only contain what was knowable at time t.**

Features use `(-inf, t]`. Labels use `(t, t+h]`. The two windows do not touch,
and `check_labels_against_raw()` verifies it by recomputing labels
from the source rather than inferring it from class balance. This is the
failure that inflates scores by 20-30 points and is invisible in the output.

--------------------------------------------------------------------------
WHY THERE IS A `y_valid` COLUMN
--------------------------------------------------------------------------
A sensor that is offline for the next three hours produces no label — not a
negative one. Missing flood readings run at 10.7% by 2025, so treating "no
reading" as "no flood" would teach the model that certain stations stopped
flooding in 2023. `y_valid_{h}h` marks rows where enough of the forward window
was actually observed; everything else must be dropped before training, not
counted as a negative.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

import pandas as pd

from .config import load_config
from .rawio import connect, interim_sql


def _tiers() -> List[int]:
    return sorted(int(t) for t in load_config()["flood_event"]["tiers_cm"].values())


def build_labels(years: Optional[Iterable[int]] = None, con=None,
                 min_valid_share: float = 0.5) -> pd.DataFrame:
    """One row per station per 15 minutes, with the forward-looking targets.

    Columns
    -------
    station_code, ts
    fl_depth_now              depth at t, in cm (this is a FEATURE, not a label)
    y_maxdepth_{h}h           deepest reading in (t, t+h]
    y_ge{tier}_{h}h           did depth reach the tier in (t, t+h]
    y_valid_{h}h              was enough of the window observed to score it
    is_onset_{tier}_{h}h      was the station BELOW the tier at t

    `is_onset_*` is evaluation metadata and must never be a model input — it is
    derived from the label window's starting condition. It exists because a
    single recall number describes a monitor: in the previous version, 55%
    headline recall was ~100% on already-flooded rows and 9% on genuine onsets.
    """
    owns = con is None
    con = con or connect()
    try:
        return con.execute(labels_sql(years, min_valid_share)).fetchdf()
    finally:
        if owns:
            con.close()


def labels_sql(years: Optional[Iterable[int]] = None,
               min_valid_share: float = 0.5) -> str:
    """The same labels as SQL, for callers that must not materialise them.

    A year of labels is 3.5 million rows. Held as a pandas frame alongside the
    feature joins it was enough, on a 3.9 GB machine, to get the process killed
    by the kernel with no traceback — which, if the output happens to be piped,
    is indistinguishable from success. `write_feature_table` therefore consumes
    this as a view and never brings it into Python.
    """
    cfg = load_config()
    cadence = cfg["data"]["cadence_minutes"]
    step = cfg["data"]["model_cadence_minutes"]
    horizons = cfg["horizons_hours"]
    tiers = _tiers()

    if True:  # keeps the body indented; the SQL is built, not executed here
        src = interim_sql("flood", years)
        per_h = 60 // cadence          # 5-min readings in an hour

        # One pass: for each horizon, the max and the count of real readings in
        # the FORWARD window, computed on the 5-minute grid so short events
        # survive. `ROWS BETWEEN 1 FOLLOWING` excludes t itself — the label may
        # not contain the present.
        agg = []
        for h in horizons:
            n = h * per_h
            # TIME-based, not row-based. On the current data this changes
            # nothing -- the 5-minute timestamp grid is complete, so counting 12
            # rows and asking for one hour agree everywhere (verified across all
            # 10.4 M readings in 2022; the missing 2.9% are NULL values in rows
            # that exist, not absent rows).
            #
            # It is written this way because `ROWS` would depend on that grid
            # staying complete, which nothing enforces. If rows ever did go
            # missing, a row-counted forward window would reach past t+h and the
            # label would absorb a flood outside the horizon it claims to cover.
            #
            # `INTERVAL '{cadence} minutes' FOLLOWING` as the lower bound is how
            # t itself is excluded: the nearest possible following reading is one
            # cadence step away, so the window is (t, t+h] exactly.
            win = (f"PARTITION BY station_code ORDER BY ts RANGE BETWEEN "
                   f"INTERVAL '{cadence} minutes' FOLLOWING "
                   f"AND INTERVAL '{h} hours' FOLLOWING")
            agg.append(f"max(flood) OVER ({win}) AS y_maxdepth_{h}h")
            agg.append(f"count(flood) OVER ({win})::DOUBLE / {n} "
                       f"AS y_obs_share_{h}h")

        out = ["station_code", "ts", "fl_depth_now"]
        for h in horizons:
            out.append(f"y_maxdepth_{h}h")
            out.append(f"y_obs_share_{h}h >= {min_valid_share} AS y_valid_{h}h")
            for tier in tiers:
                out.append(
                    f"CASE WHEN y_obs_share_{h}h >= {min_valid_share} "
                    f"THEN y_maxdepth_{h}h >= {tier} END AS y_ge{tier}_{h}h")
                # Onset = the station was BELOW the tier when the forecast was
                # made. Only these rows require forecasting; the rest are
                # answered by "it was flooded, it still is".
                out.append(f"fl_depth_now < {tier} AS is_onset_{tier}_{h}h")

        return f"""
        WITH fwd AS (
            SELECT station_code, ts, flood AS fl_depth_now, {', '.join(agg)}
            FROM {src}
        )
        SELECT {', '.join(out)} FROM fwd
        -- Down-sample to the modelling cadence only AFTER the forward windows
        -- are computed, so a 20-minute flood between two 15-minute stamps is
        -- still captured by the label.
        WHERE date_part('minute', ts)::INT % {step} = 0
        """


def label_summary(labels: pd.DataFrame) -> pd.DataFrame:
    """Positives, base rate and onset share per tier and horizon.

    The onset column is the one to read. It is the fraction of positives that
    actually needed forecasting rather than remembering.
    """
    cfg = load_config()
    rows = []
    for h in cfg["horizons_hours"]:
        valid = labels[f"y_valid_{h}h"]
        for tier in _tiers():
            y = labels.loc[valid, f"y_ge{tier}_{h}h"]
            onset = labels.loc[valid, f"is_onset_{tier}_{h}h"]
            pos = int(y.sum())
            rows.append({
                "tier_cm": tier,
                "horizon_h": h,
                "rows_scorable": int(valid.sum()),
                "positives": pos,
                "base_rate": round(pos / max(int(valid.sum()), 1), 6),
                "one_in": round(int(valid.sum()) / max(pos, 1)),
                "positives_onset": int((y & onset).sum()),
                "onset_share_of_positives": round(
                    float((y & onset).sum() / max(pos, 1)), 3),
            })
    return pd.DataFrame(rows)


def check_labels_against_raw(labels: pd.DataFrame, n_rows: int = 300,
                             years: Optional[Iterable[int]] = None,
                             con=None, seed: int = 0) -> Dict[str, object]:
    """Recompute a sample of labels straight from the 5-minute data and compare.

    WHY THIS REPLACED THE FIRST VERSION. The original check asked: "of the rows
    already at or above a tier, how many are still positive?" and treated 100%
    as evidence of leakage. It is not. Flood depth is strongly autocorrelated at
    five-minute spacing, so a station sitting at 6 cm now is almost certain to
    be above 5 cm again within the next hour. 100% was the physics, not a bug --
    and on a 20,000-row sample only 29 rows were flooded at all, so the statistic
    was noise on top of a wrong question.

    This version does the only thing that actually settles it: takes real
    (station, timestamp) pairs, recomputes `max(flood)` over `(t, t+h]` directly
    from the interim Parquet, and checks the label matches. If the window ever
    included `t`, the recomputation would disagree wherever the present reading
    is the window maximum.

    Deliberately samples rows that are FLOODED NOW as well as random ones —
    those are exactly where an off-by-one boundary would show up, and they are
    rare enough that a uniform sample would miss them.
    """
    cfg = load_config()
    cadence = cfg["data"]["cadence_minutes"]
    horizons = cfg["horizons_hours"]

    rng = labels.sample(min(n_rows, len(labels)), random_state=seed)
    flooded = labels[labels["fl_depth_now"] >= 5]
    if len(flooded):
        rng = pd.concat([rng, flooded.sample(min(n_rows, len(flooded)),
                                             random_state=seed)])
    rng = rng[["station_code", "ts", "fl_depth_now"]
              + [f"y_maxdepth_{h}h" for h in horizons]].drop_duplicates()

    owns = con is None
    con = con or connect()
    try:
        src = interim_sql("flood", years)
        probe = rng  # noqa: F841 -- DuckDB reads the local frame by name
        con.execute("CREATE OR REPLACE TEMP TABLE probe AS SELECT * FROM probe")
        checks = []
        for h in horizons:
            q = f"""
            SELECT p.station_code, p.ts, p.y_maxdepth_{h}h AS labelled,
                   (SELECT max(f.flood) FROM {src} f
                     WHERE f.station_code = p.station_code
                       AND f.ts >  p.ts
                       AND f.ts <= p.ts + INTERVAL '{h} hours') AS recomputed
            FROM probe p
            """
            got = con.execute(q).fetchdf()
            both = got.dropna(subset=["labelled", "recomputed"])
            mismatch = (both.labelled - both.recomputed).abs() > 1e-6
            checks.append({
                "horizon_h": h,
                "rows_compared": int(len(both)),
                "mismatches": int(mismatch.sum()),
                "agrees": bool(not mismatch.any()),
            })
    finally:
        if owns:
            con.close()

    return {"checks": checks,
            "passed": all(c["agrees"] for c in checks),
            "note": ("label window is (t, t+h] and excludes t; verified against "
                     "the 5-minute source, not inferred from class balance")}
