#!/usr/bin/env python3
"""Phase-0 ingestion: raw BMA CSVs -> clean Parquet + per-station quality scorecard.

Reads the raw 5-min sensor CSVs in data/{Flood,Flow,Rain,Water}_2019-2025/,
fixes every known data issue at ingestion time, and writes:

  <out>/<dataset>/<year>.parquet          (zstd, ~one station per row group)
  <out>/quality_scorecard.csv             (per station-year stats)

Known issues handled here (see docs/dataset_research_report.md):
  - literal "NULL" strings          -> real NaN
  - UTF-8 BOM on headers            -> encoding="utf-8-sig"
  - CRLF line endings               -> pandas handles transparently
  - Rain filename inconsistency     -> per-dataset filename manifest
  - Water names containing commas   -> proper CSV quoting via pandas
  - FW.PKG.01 7-year sensor fault   -> flow columns nulled + qc_flag (default)
  - stray |flow| > 1000 elsewhere   -> nulled + qc_flag
  - physically implausible rain     -> nulled + qc_flag (per-column caps)
  - implausible flood/wl values     -> nulled + qc_flag
  - Flow all-4-columns-NULL steps   -> sensor_out indicator column

Usage:
  python phase0_ingest.py --data-dir data --out-dir data/parquet
  python phase0_ingest.py --datasets flood flow --years 2019 2020
  python phase0_ingest.py --sample 500000        # quick validation run

Requires: pandas >= 2.0, pyarrow >= 14. ~52GB input; runs comfortably in
<2GB RAM thanks to chunked reads. Full pass takes on the order of an hour
on a laptop SSD.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

YEARS = [2019, 2020, 2021, 2022, 2023, 2024, 2025]
CHUNK_ROWS = 1_048_576          # ~10 stations per chunk read
ROW_GROUP_SIZE = 105_408        # ~= one station-year (leap year) per row group

# ---------------------------------------------------------------------------
# Dataset definitions
# ---------------------------------------------------------------------------

DATASETS: dict[str, dict] = {
    "flood": {
        "dir": "Flood_2019-2025",
        "filename": lambda y: f"{y}.csv",
        "rename": {"flood_code": "station_code", "flood_name": "station_name"},
        "value_cols": ["flood"],
        # depth in cm; max ever observed 148.8 (2019)
        "valid_range": {"flood": (0.0, 200.0)},
    },
    "flow": {
        "dir": "Flow_2019-2025",
        "filename": lambda y: f"{y}.csv",
        "rename": {"flow_code": "station_code", "flow_name": "station_name"},
        "value_cols": ["flow", "wl", "area", "mean_velocity"],
        # moderate negative flow is real (tidal backflow); +-1000 m3/s is the
        # physical-plausibility line (only FW.PKG.01 + 19 FW.LPW.01 rows exceed it)
        "valid_range": {"flow": (-1000.0, 1000.0), "wl": (-10.0, 10.0)},
        "faulty_stations": ["FW.PKG.01"],   # null value cols, keep timestamps
    },
    "rain": {
        "dir": "Rain_2019-2025",
        # 2019/2020 are "2019.csv"; 2021+ are "Rain 2021.csv" (space, capital R)
        "filename": lambda y: f"{y}.csv" if y <= 2020 else f"Rain {y}.csv",
        "rename": {"rain_code": "station_code", "rain_name": "station_name"},
        "value_cols": ["rf5min", "rf15min", "rf30min", "rf1hr",
                       "rf3hr", "rf6hr", "rf12hr", "rf24hr"],
        # mm; caps ~= Bangkok physical records + margin (762mm rf24hr spike in
        # 2023 is a sensor artifact). Negative rain is always invalid.
        "valid_range": {
            "rf5min": (0.0, 60.0),   "rf15min": (0.0, 120.0),
            "rf30min": (0.0, 180.0), "rf1hr": (0.0, 250.0),
            "rf3hr": (0.0, 350.0),   "rf6hr": (0.0, 400.0),
            "rf12hr": (0.0, 450.0),  "rf24hr": (0.0, 500.0),
        },
    },
    "water": {
        "dir": "Water_2019-2025",
        "filename": lambda y: f"{y}.csv",
        "rename": {"water_code": "station_code", "water_name": "station_name"},
        "value_cols": ["wl_in", "wl_out01", "wl_out02"],
        # metres (assumed MSL datum -- confirm with Data/GIS); canal levels
        "valid_range": {"wl_in": (-10.0, 10.0),
                        "wl_out01": (-10.0, 10.0), "wl_out02": (-10.0, 10.0)},
    },
}


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------

def clean_chunk(df: pd.DataFrame, spec: dict) -> pd.DataFrame:
    """Apply all cleaning rules to one raw chunk. Returns the cleaned frame."""
    df = df.rename(columns=spec["rename"])
    value_cols = spec["value_cols"]

    # "NULL" strings -> NaN, then numeric. errors="coerce" also catches any
    # other garbage tokens without crashing the run.
    for col in value_cols:
        df[col] = pd.to_numeric(df[col].replace("NULL", np.nan), errors="coerce")

    df["site_timestamp"] = pd.to_datetime(
        df["site_timestamp"], format="%Y-%m-%d %H:%M:%S.%f", errors="coerce"
    )

    qc_flag = np.zeros(len(df), dtype=bool)

    # Station-level faults: default = null all value columns but keep the
    # rows (timeline stays complete, masking stays explicit). With
    # --drop-faulty-stations the rows are removed entirely.
    faulty = spec.get("faulty_stations", [])
    if faulty:
        mask = df["station_code"].isin(faulty).to_numpy()
        if mask.any():
            if spec.get("drop_faulty"):
                df = df.loc[~mask].reset_index(drop=True)
                qc_flag = qc_flag[~mask]
            else:
                df.loc[mask, value_cols] = np.nan
                qc_flag |= mask

    # Physical-plausibility ranges: out-of-range -> NaN + flag.
    for col, (lo, hi) in spec.get("valid_range", {}).items():
        vals = df[col]
        bad = ((vals < lo) | (vals > hi)).to_numpy()
        if bad.any():
            df.loc[bad, col] = np.nan
            qc_flag |= bad

    df["qc_flag"] = qc_flag

    # Sensor-out indicator: every value column null at once.
    df["sensor_out"] = df[value_cols].isna().all(axis=1)

    df["station_code"] = df["station_code"].astype("category")
    return df


# ---------------------------------------------------------------------------
# Scorecard
# ---------------------------------------------------------------------------

def update_scorecard(acc: dict, df: pd.DataFrame, value_cols: list[str]) -> None:
    """Incrementally merge per-station stats from one cleaned chunk into acc."""
    grouped = df.groupby("station_code", observed=True)
    stats = grouped.agg(
        rows=("site_timestamp", "size"),
        qc_flagged=("qc_flag", "sum"),
        sensor_out=("sensor_out", "sum"),
        first_ts=("site_timestamp", "min"),
        last_ts=("site_timestamp", "max"),
    )
    nulls = grouped[value_cols].agg(lambda s: s.isna().sum())
    mins = grouped[value_cols].min()
    maxs = grouped[value_cols].max()

    for code, row in stats.iterrows():
        entry = acc.setdefault(code, {
            "rows": 0, "qc_flagged": 0, "sensor_out": 0,
            "first_ts": row["first_ts"], "last_ts": row["last_ts"],
            **{f"null_{c}": 0 for c in value_cols},
            **{f"min_{c}": np.inf for c in value_cols},
            **{f"max_{c}": -np.inf for c in value_cols},
        })
        entry["rows"] += int(row["rows"])
        entry["qc_flagged"] += int(row["qc_flagged"])
        entry["sensor_out"] += int(row["sensor_out"])
        if pd.notna(row["first_ts"]):
            entry["first_ts"] = min(entry["first_ts"], row["first_ts"])
        if pd.notna(row["last_ts"]):
            entry["last_ts"] = max(entry["last_ts"], row["last_ts"])
        for c in value_cols:
            entry[f"null_{c}"] += int(nulls.loc[code, c])
            if pd.notna(mins.loc[code, c]):
                entry[f"min_{c}"] = min(entry[f"min_{c}"], mins.loc[code, c])
            if pd.notna(maxs.loc[code, c]):
                entry[f"max_{c}"] = max(entry[f"max_{c}"], maxs.loc[code, c])


def finalize_scorecard(acc: dict, dataset: str, year: int) -> pd.DataFrame:
    expected = 366 * 288 if year % 4 == 0 else 365 * 288  # 5-min steps/year
    rows = []
    for code, e in sorted(acc.items()):
        rec = {
            "dataset": dataset, "year": year, "station_code": code,
            "rows": e["rows"], "expected_rows": expected,
            "complete_pct": round(100.0 * e["rows"] / expected, 2),
            "qc_flagged": e["qc_flagged"], "sensor_out": e["sensor_out"],
            "first_ts": e["first_ts"], "last_ts": e["last_ts"],
        }
        for k, v in e.items():
            if k.startswith("null_"):
                rec[k + "_pct"] = round(100.0 * v / max(e["rows"], 1), 2)
            elif k.startswith(("min_", "max_")):
                rec[k] = None if np.isinf(v) else round(float(v), 3)
        rows.append(rec)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Main conversion loop
# ---------------------------------------------------------------------------

def convert_file(csv_path: Path, out_path: Path, spec: dict, dataset: str,
                 year: int, sample: int | None) -> pd.DataFrame:
    """Stream one raw CSV to Parquet; return its slice of the scorecard."""
    t0 = time.time()
    acc: dict = {}
    writer: pq.ParquetWriter | None = None
    total = 0

    reader = pd.read_csv(
        csv_path,
        encoding="utf-8-sig",
        dtype=str,                 # everything as string; we coerce ourselves
        chunksize=CHUNK_ROWS,
        nrows=sample,
        quotechar='"',             # Water station names contain commas
        on_bad_lines="warn",
    )
    try:
        for chunk in reader:
            df = clean_chunk(chunk, spec)
            update_scorecard(acc, df, spec["value_cols"])
            table = pa.Table.from_pandas(df, preserve_index=False)
            if writer is None:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                writer = pq.ParquetWriter(out_path, table.schema,
                                          compression="zstd")
            writer.write_table(table, row_group_size=ROW_GROUP_SIZE)
            total += len(df)
    finally:
        if writer is not None:
            writer.close()

    print(f"  {csv_path.name}: {total:,} rows -> {out_path} "
          f"({time.time() - t0:.0f}s)")
    return finalize_scorecard(acc, dataset, year)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data-dir", type=Path, default=Path("data"))
    ap.add_argument("--out-dir", type=Path, default=Path("data/parquet"))
    ap.add_argument("--datasets", nargs="+", default=list(DATASETS),
                    choices=list(DATASETS))
    ap.add_argument("--years", nargs="+", type=int, default=YEARS)
    ap.add_argument("--sample", type=int, default=None,
                    help="read only the first N rows of each file (validation)")
    ap.add_argument("--drop-faulty-stations", action="store_true",
                    help="drop rows from faulty stations (e.g. FW.PKG.01) "
                         "entirely instead of nulling their value columns")
    args = ap.parse_args()

    scorecards = []
    for ds in args.datasets:
        spec = dict(DATASETS[ds])
        if args.drop_faulty_stations:
            spec["drop_faulty"] = True
        print(f"[{ds}]")
        for year in args.years:
            csv_path = args.data_dir / spec["dir"] / spec["filename"](year)
            if not csv_path.exists():
                print(f"  MISSING: {csv_path}", file=sys.stderr)
                continue
            out_path = args.out_dir / ds / f"{year}.parquet"
            sc = convert_file(csv_path, out_path, spec, ds, year, args.sample)
            if args.drop_faulty_stations and spec.get("faulty_stations"):
                sc = sc[~sc["station_code"].isin(spec["faulty_stations"])]
            scorecards.append(sc)

    if scorecards:
        card = pd.concat(scorecards, ignore_index=True)
        card_path = args.out_dir / "quality_scorecard.csv"
        card_path.parent.mkdir(parents=True, exist_ok=True)
        card.to_csv(card_path, index=False)
        print(f"\nScorecard: {card_path} ({len(card)} station-years)")
        # Loud warnings for anything incomplete
        bad = card[card["complete_pct"] < 99.9]
        if len(bad):
            print(f"WARNING: {len(bad)} station-years <99.9% complete:")
            print(bad[["dataset", "year", "station_code", "complete_pct"]]
                  .to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
