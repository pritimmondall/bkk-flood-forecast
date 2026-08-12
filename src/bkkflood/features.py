"""
Building the model-ready feature table.

--------------------------------------------------------------------------
THE ONE RULE
--------------------------------------------------------------------------
Every feature here uses only `(-inf, t]`. Nothing looks forward. Labels live in
`labels.py` and use `(t, t+h]`. If those windows ever touch, scores rise 20-30
points for a reason that has nothing to do with forecasting, and nothing in the
output looks wrong.

--------------------------------------------------------------------------
WHAT IS LOCAL AND WHAT IS NOT, AND WHY IT IS NOT OUR CHOICE
--------------------------------------------------------------------------
    flood       per station          the sensor's own history
    rain        per district         rain codes share a district prefix with
                                     flood codes -- covers 33/33 flood districts
    water       CITYWIDE             canal codes are canal names, not districts.
    flow        CITYWIDE             Only 13/33 and 3/33 districts are reachable,
                                     so a local join is impossible until BMA
                                     supplies coordinates. This is the single
                                     biggest avoidable weakness in the feature
                                     set and it is a spreadsheet away from fixed.
    terrain     per district         no station coordinates, same reason
    forecast    per district-ish     GFS is ~13 km; Bangkok is ~40 km across, so
                                     neighbouring districts share grid cells

Anything citywide tells the model that the network as a whole is under stress,
never which canal is failing next to which road.

--------------------------------------------------------------------------
NaN IS INFORMATION
--------------------------------------------------------------------------
Missing readings reach 10.7% (flood) and 15.9% (flow) by 2025 and the rate
triples after 2022. A missing reading is not a dry road, so nothing is filled.
LightGBM handles NaN natively; sequence models get an explicit indicator. The
`*_offline_share` features exist so the model can tell "no flood" from
"no sensor" — without them it would learn that certain stations stopped flooding
in 2023.
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd

from .config import load_config, resolve
from .rawio import connect, interim_sql
from .stations import district_prefix
from .evaluate import pr_auc

# Lunar periods, for reconstructing tidal phase. Real physics, and free -- but
# it gives PHASE, not HEIGHT. A spring tide during a storm surge is a completely
# different situation from a neap tide, and these terms cannot tell them apart.
# A measured Chao Phraya tide gauge is request #5 on the BMA list.
M2_HOURS = 12.4206012          # principal lunar semi-diurnal
SYNODIC_DAYS = 29.530588       # new moon to new moon: the spring-neap cycle


# ---------------------------------------------------------------------------
# Flood autoregressive — the station's own recent history
# ---------------------------------------------------------------------------
def flood_features(years: Optional[Iterable[int]] = None, con=None) -> pd.DataFrame:
    """Per-station rolling history of depth, at the modelling cadence.

    `fl_std_3h` is the one to watch. In the previous version's 15 cm / 1 h model
    it carried 68.9% of the gain, against 1.6% for the current depth level.
    Recent *variability* predicts flooding better than the level does -- which is
    the difference between a forecaster and a monitor, and the strongest single
    argument that this feature set is looking at the right thing.
    """
    owns = con is None
    con = con or connect()
    try:
        return con.execute(_flood_sql(years)).fetchdf()
    finally:
        if owns:
            con.close()


def _flood_sql(years: Optional[Iterable[int]] = None) -> str:
    """Backward windows, all of them TIME-based rather than row-based.

    HOW MUCH DIFFERENCE THIS MAKES, MEASURED: none. Over all 10,408,947 flood
    readings in 2022, `ROWS BETWEEN 36 PRECEDING` and `RANGE BETWEEN INTERVAL
    '3 hours' PRECEDING` give an identical answer on every single row.

    That was not the expectation. The reasoning for switching was that 2.9% of
    readings are missing in 2022 and 10.7% by 2025, so a 36-row window would
    stretch past three hours wherever there was a gap. It does not, because the
    missing readings are NULL *values* in rows that exist -- the timestamp grid
    is complete and unbroken. There are no missing rows to skip over.

    The time-based form is kept anyway, and the reason is worth being clear
    about: it is correct by construction rather than correct by luck. `ROWS`
    silently depends on an invariant -- a complete 5-minute grid -- that nothing
    in the pipeline enforces and that a future re-ingest could quietly break.
    `RANGE` asks for three hours and gets three hours. It costs roughly 40
    seconds per year to build instead of 10.

    (The 28 disagreements that prompted all this turned out to be the *check*
    using `> t-3h` where the window uses `>= t-3h`. The feature was right. That
    is now the fourth time in this project that a check, not the data, was the
    thing that was broken.)
    """
    cfg = load_config()
    cadence = cfg["data"]["cadence_minutes"]
    step = cfg["data"]["model_cadence_minutes"]
    expected_3h = 3 * 60 // cadence + 1
    src = interim_sql("flood", years)
    w = "PARTITION BY station_code ORDER BY ts"

    def back(interval):
        return f"{w} RANGE BETWEEN INTERVAL '{interval}' PRECEDING AND CURRENT ROW"

    def at(interval):
        # Zero-width range: exactly the reading that far back, or NULL if that
        # particular reading is missing. A lag by row count would silently
        # return whatever the previous surviving reading happened to be.
        return (f"{w} RANGE BETWEEN INTERVAL '{interval}' PRECEDING "
                f"AND INTERVAL '{interval}' PRECEDING")

    return f"""
        WITH base AS (
            SELECT station_code, ts, flood,
                   max(flood) OVER ({at(f'{step} minutes')}) AS fl_prev_step,
                   max(flood) OVER ({at('1 hour')})  AS fl_depth_lag_1h,
                   max(flood) OVER ({at('3 hours')}) AS fl_depth_lag_3h,
                   max(flood) OVER ({back('3 hours')})  AS fl_max_3h,
                   max(flood) OVER ({back('24 hours')}) AS fl_max_24h,
                   avg(flood) OVER ({back('1 hour')})   AS fl_mean_1h,
                   stddev_samp(flood) OVER ({back('3 hours')}) AS fl_std_3h,
                   count(flood) OVER ({back('3 hours')})::DOUBLE
                       / {expected_3h} AS fl_obs_share_3h,
                   -- Time since the station was last wet. `last_value ... IGNORE
                   -- NULLS` over the trailing window carries the most recent
                   -- crossing forward; NULL means "not in living memory".
                   last_value(CASE WHEN flood >= 5  THEN ts END IGNORE NULLS)
                       OVER ({w} ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS fl_last_5cm,
                   last_value(CASE WHEN flood >= 15 THEN ts END IGNORE NULLS)
                       OVER ({w} ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS fl_last_15cm
            FROM {src}
        )
        SELECT station_code, ts,
               flood                          AS fl_depth_now,
               fl_depth_lag_1h, fl_depth_lag_3h,
               flood - fl_prev_step           AS fl_rise_15min,
               flood - fl_depth_lag_1h        AS fl_rise_1h,
               fl_max_3h, fl_max_24h, fl_mean_1h, fl_std_3h,
               least(1.0, 1.0 - fl_obs_share_3h) AS fl_missing_share_3h,
               date_diff('minute', fl_last_5cm,  ts) / 60.0 AS fl_hours_since_5cm,
               date_diff('minute', fl_last_15cm, ts) / 60.0 AS fl_hours_since_15cm
        FROM base
        WHERE date_part('minute', ts)::INT % {step} = 0
        """


# ---------------------------------------------------------------------------
# Rain — the only input that can be joined locally
# ---------------------------------------------------------------------------
def rain_features(years: Optional[Iterable[int]] = None, con=None) -> pd.DataFrame:
    """Rainfall aggregated per district per 15 minutes.

    `rain_spread` (max minus mean across the gauges in a district) is the closest
    thing available to a measure of how localised the rain is. It is a poor
    substitute for radar: one gauge per ~12 km2 against cells 2-5 km across, so
    the average smooths away the peak that causes the flood. That gap is the
    single biggest expected accuracy gain in the project.
    """
    owns = con is None
    con = con or connect()
    try:
        return con.execute(_rain_sql(years)).fetchdf()
    finally:
        if owns:
            con.close()


def _rain_sql(years: Optional[Iterable[int]] = None) -> str:
    cfg = load_config()
    step = cfg["data"]["model_cadence_minutes"]
    per_step = 60 // step
    src = interim_sql("rain", years)
    w = "PARTITION BY district_code ORDER BY ts"
    return f"""
    WITH d AS (
        SELECT split_part(station_code, '.', 2) AS district_code, ts,
               avg(rf1hr)  AS rain_rf1hr_mean,  max(rf1hr)  AS rain_rf1hr_max,
               avg(rf3hr)  AS rain_rf3hr_mean,  max(rf3hr)  AS rain_rf3hr_max,
               avg(rf6hr)  AS rain_rf6hr_mean,
               avg(rf24hr) AS rain_rf24hr_mean,
               max(rf1hr) - avg(rf1hr) AS rain_spread,
               count(rf1hr) AS rain_gauges_reporting
        FROM {src}
        WHERE date_part('minute', ts)::INT % {step} = 0
        GROUP BY 1, 2
    )
    SELECT *,
           rain_rf1hr_mean - lag(rain_rf1hr_mean, {per_step})     OVER ({w})
               AS rain_rf1hr_delta1h,
           rain_rf1hr_mean - lag(rain_rf1hr_mean, {3 * per_step}) OVER ({w})
               AS rain_rf1hr_delta3h,
           -- How wet was it already before today's rain: the last 24 h against
           -- the 24 h ending two days ago. Saturated ground floods on rain that
           -- dry ground absorbs. NULLIF keeps a dry baseline from dividing by 0.
           rain_rf24hr_mean / nullif(
               lag(rain_rf24hr_mean, {48 * per_step}) OVER ({w}), 0)
               AS rain_antecedent_ratio
    FROM d
    """


# ---------------------------------------------------------------------------
# Water and flow — citywide only, until coordinates arrive
# ---------------------------------------------------------------------------
def water_flow_features(years: Optional[Iterable[int]] = None, con=None) -> pd.DataFrame:
    """Citywide canal state: is the network rising, and is anything backflowing.

    Excludes the two river-scale gauges and the dead sensor named in config.
    FW.PKG.01 and FW.LPW.01 are Chao Phraya gauges reading up to 3,800 m3/s
    against a canal median under 100 -- averaging them in destroys the canal
    signal. They are not faulty, they are the wrong scale.
    """
    owns = con is None
    con = con or connect()
    try:
        return con.execute(_waterflow_sql(years)).fetchdf()
    finally:
        if owns:
            con.close()


def _waterflow_sql(years: Optional[Iterable[int]] = None) -> str:
    cfg = load_config()
    step = cfg["data"]["model_cadence_minutes"]
    ex = cfg["exclusions"]
    drop = list(ex["flow_stations_from_canal_aggregate"]) + list(ex["dead_sensors"])
    drop_sql = ", ".join(f"'{s}'" for s in drop)
    wsrc, fsrc = interim_sql("water", years), interim_sql("flow", years)
    per_h = 60 // cfg["data"]["cadence_minutes"]
    return f"""
        WITH w AS (
            SELECT station_code, ts, wl_in,
                   wl_in - lag(wl_in, {per_h})     OVER (PARTITION BY station_code ORDER BY ts) AS rise_1h,
                   wl_in - lag(wl_in, {3 * per_h}) OVER (PARTITION BY station_code ORDER BY ts) AS rise_3h
            FROM {wsrc}
        ),
        wagg AS (
        SELECT ts,
               avg(rise_1h) AS water_rise_1h_mean,
               max(rise_1h) AS water_rise_1h_max,
               avg(rise_3h) AS water_rise_3h_mean,
               avg(CASE WHEN rise_1h > 0 THEN 1.0 WHEN rise_1h IS NULL THEN NULL ELSE 0.0 END)
                   AS water_rising_share,
               avg(CASE WHEN wl_in IS NULL THEN 1.0 ELSE 0.0 END) AS water_offline_share
        FROM w
        WHERE date_part('minute', ts)::INT % {step} = 0
        GROUP BY 1
        ),
        fagg AS (
        SELECT ts,
               avg(CASE WHEN station_code NOT IN ({drop_sql}) THEN flow END) AS flow_mean,
               avg(CASE WHEN station_code NOT IN ({drop_sql}) THEN mean_velocity END)
                   AS flow_velocity_mean,
               avg(CASE WHEN station_code IN ({drop_sql}) THEN NULL
                        WHEN flow < 0 THEN 1.0 WHEN flow IS NULL THEN NULL ELSE 0.0 END)
                   AS flow_negative_share,
               avg(CASE WHEN flow IS NULL THEN 1.0 ELSE 0.0 END) AS flow_offline_share
        FROM {fsrc}
        WHERE date_part('minute', ts)::INT % {step} = 0
        GROUP BY 1
        )
        SELECT * FROM wagg FULL OUTER JOIN fagg USING (ts)
    """


# ---------------------------------------------------------------------------
# Calendar and tide
# ---------------------------------------------------------------------------
def calendar_features(ts: pd.Series) -> pd.DataFrame:
    """Cyclical time, monsoon flag, and reconstructed tidal phase.

    The tide terms are astronomy, not measurement: they place you correctly in
    the M2 and spring-neap cycles but say nothing about height. Labelled here so
    nobody downstream mistakes them for a gauge.
    """
    t = pd.to_datetime(ts)
    hour = t.dt.hour + t.dt.minute / 60.0
    doy = t.dt.dayofyear
    # Hours since an arbitrary fixed epoch -- only the phase matters, not the origin.
    since = (t - pd.Timestamp("2019-01-01")).dt.total_seconds() / 3600.0

    return pd.DataFrame({
        "cal_hour_sin": np.sin(2 * np.pi * hour / 24),
        "cal_hour_cos": np.cos(2 * np.pi * hour / 24),
        "cal_doy_sin": np.sin(2 * np.pi * doy / 365.25),
        "cal_doy_cos": np.cos(2 * np.pi * doy / 365.25),
        "cal_monsoon": t.dt.month.between(5, 10).astype("float32"),
        "tide_m2_sin": np.sin(2 * np.pi * since / M2_HOURS),
        "tide_m2_cos": np.cos(2 * np.pi * since / M2_HOURS),
        "tide_spring_neap": np.cos(2 * np.pi * since / (SYNODIC_DAYS * 24)),
    }, index=t.index)


# ---------------------------------------------------------------------------
# External rainfall
# ---------------------------------------------------------------------------
def external_rain(district_by_code: Dict[str, str]) -> pd.DataFrame:
    """GFS forecast rain and ERA5 past rain, keyed by district code.

    THE DISTINCTION THAT MATTERS. `fcst_*` is what the weather model PREDICTED at
    the time and is legitimate as a forecast feature. `era5_*` is what actually
    FELL, reconstructed afterwards -- legitimate as past rain, never as a
    forecast. Using ERA5 as `rain_fcst_*` trains the model on the answer sheet;
    it scores beautifully and collapses on the first live day.

    That is not hypothetical: it happened in this project on 8 August 2026, and
    `assert_forecast_is_not_reanalysis()` exists because the naming convention
    alone did not catch it. Call that guard before using these columns.
    """
    cfg = load_config()
    om = cfg["external"]["open_meteo"]
    name_to_code = {v: k for k, v in district_by_code.items()}

    out = []
    for path, prefix in ((om["forecast"]["out"], "fcst"), (om["observed"]["out"], "era5")):
        df = pd.read_parquet(resolve(path))
        df["district_code"] = df["district"].map(name_to_code)
        df = df.dropna(subset=["district_code"])
        keep = [c for c in df.columns if c.startswith(f"{prefix}_")]
        out.append(df[["district_code", "ts"] + keep])

    merged = out[0].merge(out[1], on=["district_code", "ts"], how="outer")
    return merged.sort_values(["district_code", "ts"])


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def _district_code_map() -> Dict[str, str]:
    """Map station-code prefix -> district name, from the registry.

    The district assignment is trustworthy even though the coordinates are not:
    it comes from the code prefix, not from a guessed position.
    """
    from .stations import load_registry
    reg = load_registry()
    reg = reg.dropna(subset=["district"])
    reg["code"] = reg.station_code.map(district_prefix)
    alias = load_config()["terrain"].get("district_name_aliases", {})
    reg["district"] = reg["district"].map(lambda d: alias.get(d, d))
    return (reg.drop_duplicates("code").set_index("code")["district"].to_dict())


def _external_frame() -> pd.DataFrame:
    """GFS forward rain and ERA5 past rain, hourly, keyed by district code.

    ----------------------------------------------------------------------
    A CAVEAT ON `rain_fcst_*` THAT MUST NOT BE LOST
    ----------------------------------------------------------------------
    `rain_fcst_{h}h` is the rainfall the weather model expected over `(t, t+h]`,
    taken from Open-Meteo's archived-forecast series. That series is stitched
    from the *first hours of each successive model run*, so the value at t+6h
    came from a run launched a few hours before t+6h -- possibly after t.

    At 1 hour this is harmless. At 6 hours the feature may carry a little
    information that was not strictly available at t, which would make the
    6-hour model look slightly better in testing than in production.

    It is written down rather than hidden because it is the same shape as the
    ERA5 mistake this project already made once. If Phase 5 shows the 6-hour
    model leaning on it, the fix is Open-Meteo's Previous Runs API, which serves
    each variable at a fixed lead time instead of stitching.
    """
    cfg = load_config()
    om = cfg["external"]["open_meteo"]
    horizons = cfg["horizons_hours"]

    frames = []
    for path, prefix in ((om["forecast"]["out"], "fcst"),
                         (om["observed"]["out"], "era5")):
        df = pd.read_parquet(resolve(path))
        col = next(c for c in df.columns if c.startswith(f"{prefix}_") and "precip" in c)
        frames.append(df[["district", "ts", col]].rename(columns={col: prefix}))

    ext = frames[0].merge(frames[1], on=["district", "ts"], how="outer")
    ext["ts"] = pd.to_datetime(ext.ts)
    ext = ext.sort_values(["district", "ts"]).set_index("ts")

    out = []
    for name, g in ext.groupby("district"):
        row = {"district": name}
        for h in horizons:
            # Sum over (t, t+h]: roll backward, then move the stamp back h hours.
            row[f"rain_fcst_{h}h"] = g["fcst"].rolling(f"{h}h").sum().shift(-h, freq="h")
        # ERA5 is PAST rain only -- what fell in the hours BEFORE t.
        row["era5_rain_3h"] = g["era5"].rolling("3h").sum()
        out.append(pd.DataFrame(row).reset_index())
    return pd.concat(out, ignore_index=True).sort_values(["ts", "district"])


def _terrain_frame() -> Optional[pd.DataFrame]:
    """District terrain, renamed with a `terr_` prefix. None if Phase 1 not run."""
    path = resolve("data/features/terrain_district_ground.parquet")
    if not path.exists():
        return None
    terr = pd.read_parquet(path)
    want = ["district", "elev_m_p50", "elev_m_p10", "depression_depth_m_p95",
            "depressed_area_share", "slope_deg_p50", "twi_mean", "log_flow_acc_p95"]
    terr = terr[[c for c in want if c in terr.columns]].copy()
    terr.columns = ["district"] + [f"terr_{c}" for c in terr.columns[1:]]
    return terr


def write_feature_table(year: int, con=None, out: Optional[str] = None) -> str:
    """Build one year of model-ready rows and write it to Parquet.

    THE JOINS HAPPEN IN DUCKDB, NOT PANDAS, and that is not a style choice. A
    year is 3.5 million rows by ~55 columns; assembling it with `pandas.merge`
    peaked over the 3.9 GB the machine has and the process was killed with no
    traceback -- an out-of-memory kill looks exactly like a silent success if
    the output is piped. DuckDB streams the joins and spills to disk, and `COPY`
    writes the result without ever holding the whole table in memory.

    Everything is cast to FLOAT (32-bit) on the way out. Sensor readings carry
    two or three significant figures; 64-bit doubles store noise at twice the
    price.
    """
    cfg = load_config()
    out = out or f"data/features/features_{year}.parquet"
    dest = resolve(out)
    dest.parent.mkdir(parents=True, exist_ok=True)

    owns = con is None
    con = con or connect()
    try:
        from .labels import labels_sql
        con.execute(f"CREATE OR REPLACE TEMP VIEW v_flood AS {_flood_sql([year])}")
        con.execute(f"CREATE OR REPLACE TEMP VIEW v_rain  AS {_rain_sql([year])}")
        con.execute(f"CREATE OR REPLACE TEMP VIEW v_wf    AS {_waterflow_sql([year])}")
        con.execute(f"CREATE OR REPLACE TEMP VIEW v_lab   AS {labels_sql([year])}")

        lab_cols = [d[0] for d in con.execute(
            "SELECT * FROM v_lab LIMIT 0").description]
        # Prefix -> district NAME. Joining terrain and external data on the
        # name is not cosmetic: 97 station prefixes map onto 49 districts,
        # because rain, water, flow and flood each use their own prefix for the
        # same place. Inverting that map to name -> prefix keeps one arbitrary
        # prefix per district and silently drops the rest -- it cost 16 of the
        # 33 flood districts their terrain, and showed up only as an oddly
        # round 46.1% null rate appearing in two unrelated feature blocks at
        # once.
        dmap = pd.DataFrame(sorted(_district_code_map().items()),
                            columns=["district_code", "district"])
        con.register("t_dmap", dmap)
        ext = _external_frame()
        con.register("t_ext", ext[ext.ts.dt.year == year])
        terr = _terrain_frame()
        has_terr = terr is not None
        if has_terr:
            con.register("t_terr", terr)

        label_cols = [c for c in lab_cols
                      if c not in ("station_code", "ts", "fl_depth_now")]
        ext_cols = [c for c in ext.columns if c not in ("district", "ts")]
        terr_cols = ([c for c in terr.columns if c != "district"]
                     if has_terr else [])

        # Float32 everywhere except the label booleans and the keys.
        def cast(cols, src):
            return ", ".join(
                f"{src}.{c}" if c.startswith(("y_valid", "y_ge", "is_onset"))
                else f"{src}.{c}::FLOAT AS {c}" for c in cols)

        sel = [
            "f.station_code", "f.ts", "f.district_code", "d.district",
            cast([c for c in _FLOOD_COLS], "f"),
            cast(label_cols, "l"),
            cast([c for c in _RAIN_COLS], "r"),
            cast([c for c in _WF_COLS], "w"),
            cast(ext_cols, "e"),
        ]
        if has_terr:
            sel.append(cast(terr_cols, "g"))
        sel.append(_CALENDAR_SQL)
        sel.append("r.rain_rf1hr_mean::FLOAT * f.fl_max_24h::FLOAT AS rain_x_recent_flood")
        if has_terr:
            sel.append("r.rain_rf1hr_mean::FLOAT * g.terr_depression_depth_m_p95::FLOAT "
                       "AS rain_x_depression")
            sel.append("'district' AS terr_granularity")

        terr_join = ("LEFT JOIN t_terr g ON g.district = d.district"
                     if has_terr else "")
        q = f"""
        COPY (
            WITH f AS (
                SELECT *, split_part(station_code, '.', 2) AS district_code
                FROM v_flood
            )
            SELECT {', '.join(sel)}
            FROM f
            LEFT JOIN v_lab    l ON l.station_code = f.station_code AND l.ts = f.ts
            LEFT JOIN v_rain   r ON r.district_code = f.district_code AND r.ts = f.ts
            LEFT JOIN v_wf     w ON w.ts = f.ts
            LEFT JOIN t_dmap   d ON d.district_code = f.district_code
            -- The external series is strictly hourly and the grid is 15-minute,
            -- so this is an exact match on the containing hour rather than an
            -- ASOF join. Deliberate: ASOF would carry the last known value
            -- forward across a gap, and 2021 begins on 23 March -- every row
            -- before that would have quietly inherited nothing, or worse, a
            -- neighbouring hour. A missing hour must stay missing.
            LEFT JOIN t_ext e
                 ON e.district = d.district AND e.ts = date_trunc('hour', f.ts)
            {terr_join}
        ) TO '{dest}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
        con.execute(q)
    finally:
        if owns:
            con.close()
    return str(dest)


_FLOOD_COLS = ["fl_depth_now", "fl_depth_lag_1h", "fl_depth_lag_3h", "fl_rise_15min",
               "fl_rise_1h", "fl_max_3h", "fl_max_24h", "fl_mean_1h", "fl_std_3h",
               "fl_missing_share_3h", "fl_hours_since_5cm", "fl_hours_since_15cm"]
_RAIN_COLS = ["rain_rf1hr_mean", "rain_rf1hr_max", "rain_rf3hr_mean", "rain_rf3hr_max",
              "rain_rf6hr_mean", "rain_rf24hr_mean", "rain_spread",
              "rain_gauges_reporting", "rain_rf1hr_delta1h", "rain_rf1hr_delta3h",
              "rain_antecedent_ratio"]
_WF_COLS = ["water_rise_1h_mean", "water_rise_1h_max", "water_rise_3h_mean",
            "water_rising_share", "water_offline_share", "flow_mean",
            "flow_velocity_mean", "flow_negative_share", "flow_offline_share"]

# Cyclical time and reconstructed tidal phase, computed in SQL so the whole
# table can be built without materialising it. The tide terms are astronomy,
# not measurement: they place you correctly in the M2 and spring-neap cycles
# but say nothing about HEIGHT. A spring tide during a storm surge and a spring
# tide on a calm day are identical here. A real Chao Phraya tide gauge is
# request #5 on the BMA list.
_CALENDAR_SQL = f"""
    sin(2*pi()*(date_part('hour', f.ts) + date_part('minute', f.ts)/60.0)/24)::FLOAT AS cal_hour_sin,
    cos(2*pi()*(date_part('hour', f.ts) + date_part('minute', f.ts)/60.0)/24)::FLOAT AS cal_hour_cos,
    sin(2*pi()*date_part('dayofyear', f.ts)/365.25)::FLOAT AS cal_doy_sin,
    cos(2*pi()*date_part('dayofyear', f.ts)/365.25)::FLOAT AS cal_doy_cos,
    (date_part('month', f.ts) BETWEEN 5 AND 10)::FLOAT AS cal_monsoon,
    sin(2*pi()*(epoch(f.ts - TIMESTAMP '2019-01-01')/3600.0)/{M2_HOURS})::FLOAT AS tide_m2_sin,
    cos(2*pi()*(epoch(f.ts - TIMESTAMP '2019-01-01')/3600.0)/{M2_HOURS})::FLOAT AS tide_m2_cos,
    cos(2*pi()*(epoch(f.ts - TIMESTAMP '2019-01-01')/3600.0)/{SYNODIC_DAYS * 24})::FLOAT AS tide_spring_neap
"""


def feature_columns(df: pd.DataFrame) -> List[str]:
    """Model inputs only. Excludes labels, keys and evaluation metadata.

    `is_onset_*` is deliberately excluded: it is derived from the label window's
    starting condition and exists to split recall into onset and ongoing when
    reporting. Feeding it to a model would be leakage of the mildest and most
    embarrassing kind.
    """
    drop_exact = {"station_code", "ts", "district", "district_code", "terr_granularity"}
    return [c for c in df.columns
            if c not in drop_exact and not c.startswith(("y_", "is_onset_"))]


def check_features_against_raw(year: int, n_rows: int = 200, con=None,
                               seed: int = 0) -> Dict[str, object]:
    """Recompute a sample of rolling features from the 5-minute source.

    Same philosophy as `check_labels_against_raw`: recompute, do not infer. Four
    times in this project a *check* was wrong rather than the data -- absence
    read as difference, a masked surface compared against itself, an absolute
    count used where a density was needed, and autocorrelation mistaken for
    leakage. Every one of those was a check that reasoned from summary
    statistics instead of going back to the source.

    Verifies two things that would be invisible otherwise:
      * `fl_max_3h` really is the maximum over `(t-3h, t]` and INCLUDES t
      * it does not include a single reading after t

    The second is the one that matters. A window written `BETWEEN 3 PRECEDING
    AND 1 FOLLOWING` instead of `AND CURRENT ROW` produces a feature that looks
    entirely reasonable, correlates beautifully with the label, and is worthless.
    """
    owns = con is None
    con = con or connect()
    try:
        src = interim_sql("flood", [year])
        feat = resolve(f"data/features/features_{year}.parquet")
        # Sample WET rows, not random ones. On a uniform sample almost every row
        # is a flat zero, where a forward-looking window and a backward-looking
        # one give the same answer -- the first version of this check compared
        # 192 rows and only ONE of them could have distinguished the two. A
        # check that cannot fail is not a check.
        # `USING SAMPLE` is applied BEFORE the filter -- the optimiser pushes it
        # down -- so asking for 200 wet rows returned 1. Ordering by a hash is
        # deterministic, respects the filter, and needs no seed.
        con.execute(f"""
        CREATE OR REPLACE TEMP TABLE probe_feat AS
        (SELECT station_code, ts, fl_depth_now, fl_max_3h FROM '{feat}'
          WHERE fl_max_3h > 0
          ORDER BY hash(station_code || ts::VARCHAR || {seed}) LIMIT {n_rows})
        UNION ALL
        (SELECT station_code, ts, fl_depth_now, fl_max_3h FROM '{feat}'
          WHERE fl_max_3h IS NOT NULL
          ORDER BY hash(ts::VARCHAR || station_code || {seed}) LIMIT {n_rows // 4})
        """)
        got = con.execute(f"""
        SELECT p.*,
               (SELECT max(s.flood) FROM {src} s
                 WHERE s.station_code = p.station_code
                   -- >=, not >. The window is the CLOSED interval [t-3h, t]:
                   -- 37 readings at 5-minute spacing, matching
                   -- `RANGE BETWEEN INTERVAL '3 hours' PRECEDING AND CURRENT
                   -- ROW`. Writing `>` here made the check disagree with the
                   -- feature on 28 of 250 rows -- the reading at exactly t-3h,
                   -- whenever it happened to be the window maximum. The feature
                   -- was right and the check was wrong, which is now the fourth
                   -- time that has happened in this project.
                   AND s.ts >= p.ts - INTERVAL '3 hours'
                   AND s.ts <= p.ts)                       AS recomputed_incl_t,
               (SELECT max(s.flood) FROM {src} s
                 WHERE s.station_code = p.station_code
                   AND s.ts >  p.ts
                   AND s.ts <= p.ts + INTERVAL '3 hours')  AS future_only
        FROM probe_feat p
        """).fetchdf()
    finally:
        if owns:
            con.close()

    ok = got.dropna(subset=["fl_max_3h", "recomputed_incl_t"])
    matches = (ok.fl_max_3h - ok.recomputed_incl_t).abs() <= 1e-4
    # Where the future is strictly higher than the past window, the feature must
    # follow the PAST. If it tracks the future instead, the window looks forward.
    fut = got.dropna(subset=["fl_max_3h", "future_only", "recomputed_incl_t"])
    fut = fut[fut.future_only > fut.recomputed_incl_t + 1e-4]
    leaked = int((fut.fl_max_3h > fut.recomputed_incl_t + 1e-4).sum())

    return {
        "rows_compared": int(len(ok)),
        "mismatches": int((~matches).sum()),
        "rows_where_future_is_higher": int(len(fut)),
        "rows_that_tracked_the_future": leaked,
        "passed": bool(matches.all() and leaked == 0),
        "note": "fl_max_3h recomputed over (t-3h, t] from the 5-minute source",
    }


def load_features(years: Iterable[int], columns: Optional[Sequence[str]] = None,
                  tier_cm: Optional[int] = None, horizon_h: Optional[int] = None,
                  scorable_only: bool = False, con=None) -> pd.DataFrame:
    """Read built feature Parquet back, a few columns at a time.

    ALWAYS PASS `columns`. A year is 3.5 million rows by 79 columns; two years
    read in full is roughly 2 GB of pandas and this project has already been
    OOM-killed once doing exactly that, silently, with the traceback swallowed
    by a pipe. Baselines need seven columns and a fold needs two years.

    `tier_cm` and `horizon_h` add the matching label, validity flag and onset
    flag, so callers do not have to spell out the naming convention and cannot
    accidentally score rows whose forward window was never observed.
    """
    cols = list(columns) if columns else None
    if cols is not None:
        for c in ("station_code", "ts"):
            if c not in cols:
                cols.insert(0, c)
        if tier_cm is not None and horizon_h is not None:
            for c in (f"y_ge{tier_cm}_{horizon_h}h", f"y_valid_{horizon_h}h",
                      f"is_onset_{tier_cm}_{horizon_h}h",
                      f"y_maxdepth_{horizon_h}h"):
                if c not in cols:
                    cols.append(c)

    paths = [str(resolve(f"data/features/features_{y}.parquet")) for y in years]
    missing = [p for p in paths if not pd.io.common.file_exists(p)]
    if missing:
        raise FileNotFoundError(
            f"build these first with write_feature_table(): {missing}")

    sel = ", ".join(cols) if cols else "*"
    where = (f"WHERE y_valid_{horizon_h}h"
             if scorable_only and horizon_h is not None else "")
    owns = con is None
    con = con or connect()
    try:
        return con.execute(
            f"SELECT {sel} FROM read_parquet({paths}) {where} ORDER BY ts"
        ).fetchdf()
    finally:
        if owns:
            con.close()


def forecast_value_test(years: Sequence[int], tier_cm: int = 15,
                        horizon_h: int = 3, con=None) -> Dict[str, pd.DataFrame]:
    """Does GFS forecast rain earn its place in the feature set? Measure, then decide.

    The question is not "is GFS a good weather model". It is narrower and
    harsher: **given that we already know what the BMA gauges recorded up to
    time t, does knowing what GFS expects for the next few hours help predict a
    road flood?**

    Three tests, in increasing order of what they actually settle:

    1. **Meteorological skill.** Compare the forecast for an hour against what
       the gauges recorded in that hour. Reported on WET hours only. Roughly
       three quarters of hours are dry, so an overall agreement rate of 70%
       measures nothing but the dry ones — this project has already been misled
       by exactly that statistic once.

    2. **Standalone discrimination.** PR-AUC of each rain variable on its own
       against the flood label. Establishes whether the forecast carries any
       signal at all.

    3. **Marginal contribution — the one that decides it.** Compare gauge rain
       alone against gauge rain PLUS the forecast, as `past 3 h observed +
       next 3 h expected`, which is a physically meaningful quantity in
       millimetres rather than an arbitrary combination. Reported separately on
       ONSET rows, because that is the only subset where a forecast could help:
       on rows that are already flooded, the current depth answers the question
       and the rain is irrelevant.

    If test 3 shows nothing on onsets, `rain_fcst_*` should be dropped. It is
    the only feature block with a fold problem (GFS starts 23 March 2021, so
    fold 1 trains on years with no forecast at all), and dropping it makes that
    problem disappear rather than needing to be managed.
    """
    cols = ["rain_rf1hr_mean", "rain_rf3hr_mean", "rain_fcst_1h",
            f"rain_fcst_{horizon_h}h", "district", "fl_depth_now"]
    df = load_features(years, cols, tier_cm=tier_cm, horizon_h=horizon_h, con=con)

    # --- 1. meteorological skill, on wet hours ------------------------------
    d = (df[["district", "ts", "rain_rf1hr_mean", "rain_fcst_1h"]]
         .drop_duplicates(["district", "ts"]).sort_values(["district", "ts"]))
    d["ts_hour"] = pd.to_datetime(d.ts).dt.floor("h")
    hourly = (d.groupby(["district", "ts_hour"])
                .agg(gauge=("rain_rf1hr_mean", "mean"),
                     fcst=("rain_fcst_1h", "mean")).reset_index())
    # What the gauges recorded in the hour the forecast was FOR.
    hourly["gauge_next"] = hourly.groupby("district")["gauge"].shift(-1)
    h = hourly.dropna(subset=["fcst", "gauge_next"])
    wet = h[(h.gauge_next >= 0.1) | (h.fcst >= 0.1)]
    skill = pd.DataFrame([{
        "hours_compared": len(h),
        "share_of_hours_dry_both_ways": float((~((h.gauge_next >= 0.1) |
                                                 (h.fcst >= 0.1))).mean()),
        "wet_hours": len(wet),
        "wet_hour_correlation": float(wet.gauge_next.corr(wet.fcst)),
        "wet_hour_hit_rate": float(((wet.gauge_next >= 0.1) &
                                    (wet.fcst >= 0.1)).mean()),
        "mean_gauge_mm_when_wet": float(wet.gauge_next.mean()),
        "mean_fcst_mm_when_wet": float(wet.fcst.mean()),
    }])

    # --- 2 and 3. value against the flood label -----------------------------
    y_col, on_col = f"y_ge{tier_cm}_{horizon_h}h", f"is_onset_{tier_cm}_{horizon_h}h"
    v = df[df[f"y_valid_{horizon_h}h"].fillna(False)]
    y = v[y_col].fillna(False).to_numpy(dtype=bool)
    onset = v[on_col].fillna(False).to_numpy(dtype=bool)

    gauge_past = v["rain_rf3hr_mean"].to_numpy(dtype="float64")
    fcst_fwd = v[f"rain_fcst_{horizon_h}h"].to_numpy(dtype="float64")
    combined = gauge_past + np.nan_to_num(fcst_fwd, nan=0.0)

    # THE CONTROL. A forecast with a wet-hour correlation of 0.015 should not be
    # able to improve anything, so any gain it shows is probably not forecast
    # skill -- it is GFS knowing that August in Bangkok is wetter than January.
    # Seasonality is real information, but `cal_monsoon` and `cal_doy_*` already
    # carry it for free and without a fold problem.
    #
    # This control replaces each forecast value with the average forecast for
    # that district, month and hour: a series with all of the seasonality and
    # none of the day-to-day skill. If the gain survives against THIS, the
    # forecast is contributing something a calendar cannot.
    ts = pd.to_datetime(v["ts"])
    seasonal_key = pd.DataFrame({
        "district": v["district"].to_numpy(),
        "month": ts.dt.month.to_numpy(),
        "hour": ts.dt.hour.to_numpy(),
        "fcst": fcst_fwd,
    })
    seasonal = (seasonal_key.groupby(["district", "month", "hour"])["fcst"]
                            .transform("mean").to_numpy(dtype="float64"))
    combined_seasonal = gauge_past + np.nan_to_num(seasonal, nan=0.0)

    candidates = {
        "gauge_past_3h": gauge_past,
        f"gfs_forecast_next_{horizon_h}h": fcst_fwd,
        "gauge_past_plus_forecast": combined,
        "gauge_past_plus_SEASONAL_control": combined_seasonal,
        "current_depth (reference)": v["fl_depth_now"].to_numpy(dtype="float64"),
    }
    rows = []
    for name, s in candidates.items():
        rows.append({
            "score": name,
            "pr_auc_all": pr_auc(y, s),
            "pr_auc_onset_only": pr_auc(y[onset], s[onset]),
            "positives_all": int(y.sum()),
            "positives_onset": int(y[onset].sum()),
        })
    value = pd.DataFrame(rows)
    base = float(y.mean())
    value["base_rate"] = base
    value["lift_over_base_onset"] = (value.pr_auc_onset_only
                                     / max(float(y[onset].mean()), 1e-12))

    def onset_auc(name):
        return float(value.loc[value.score == name, "pr_auc_onset_only"].iloc[0])

    gain = onset_auc("gauge_past_plus_forecast") - onset_auc("gauge_past_3h")
    gain_seasonal = onset_auc("gauge_past_plus_SEASONAL_control") - onset_auc("gauge_past_3h")
    verdict = pd.DataFrame([{
        "onset_pr_auc_gain_from_forecast": gain,
        "onset_pr_auc_gain_from_seasonality_alone": gain_seasonal,
        "gain_attributable_to_actual_forecast_skill": gain - gain_seasonal,
        "years": list(years),
        "tier_cm": tier_cm,
        "horizon_h": horizon_h,
        "rows_scored": int(len(v)),
    }])
    return {"meteorological_skill": skill, "value_against_label": value,
            "verdict": verdict}
