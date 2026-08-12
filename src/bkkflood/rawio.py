"""
Reading the raw CSVs, and turning them into Parquet.

The four raw datasets share three quirks that will silently corrupt your data
if you ignore them:

  1. Every header line starts with a UTF-8 byte-order mark, so the first column
     name comes back as "\\ufeffrain_code" unless you read with utf-8-sig.
  2. Missing values are the literal four-character text NULL, so a column that
     is mostly missing gets parsed as text instead of numbers.
  3. The *_name columns are Thai free text containing commas, so a naive
     line.split(",") shifts every field after it.

Everything in this module handles all three. Use it rather than pandas.read_csv.

We use DuckDB for the heavy reading because the archive is 54.8 GB and DuckDB
streams it in a fixed memory budget: a full scan of all 28 files finishes in
about five minutes inside a 2 GB cap.
"""

from __future__ import annotations

import datetime as dt
import json
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import duckdb

from .config import load_config, resolve

#: The four raw datasets, in the order they are cheapest to process.
DATASETS: List[str] = ["flood", "flow", "rain", "water"]


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------
def connect(memory_limit: Optional[str] = None, threads: Optional[int] = None):
    """Open a DuckDB connection configured from config.yaml.

    The memory limit is not decoration — it is what lets a 54.8 GB scan run on
    a laptop. DuckDB spills to `temp_directory` rather than dying.
    """
    cfg = load_config()
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{memory_limit or cfg['compute']['memory_limit']}'")
    con.execute(f"SET threads={threads or cfg['compute']['threads']}")

    # Spill files go to the OS temp directory, never into the repository.
    # (On some mounted/network filesystems a process cannot delete files it
    # created, and DuckDB then dies mid-query trying to clean up.)
    configured = cfg["compute"].get("temp_directory")
    tmp = Path(configured) if configured else Path(tempfile.gettempdir()) / "bkkflood_duckdb"
    tmp.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory='{tmp}'")
    # Insertion order is preserved deliberately. The raw CSVs already arrive
    # sorted by station then timestamp, so keeping that order means we never
    # have to pay for a 31-million-row sort during ingestion. `verify_ordering`
    # below checks the assumption rather than trusting it.
    con.execute("SET preserve_insertion_order=true")
    # Progress bars are ANSI escape sequences; in a notebook they turn into
    # hundreds of lines of unreadable output saved into the .ipynb.
    con.execute("SET enable_progress_bar=false")
    return con


# ---------------------------------------------------------------------------
# Finding files
# ---------------------------------------------------------------------------
def raw_file(dataset: str, year: int) -> Path:
    """Return the raw CSV for one dataset-year.

    Handles the inconsistent rain filenames (2019.csv but "Rain 2021.csv").
    """
    cfg = load_config()
    folder = resolve(cfg["paths"]["raw"][dataset])
    for pattern in cfg["data"]["filename_patterns"][dataset]:
        candidate = folder / pattern.format(year=year)
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"No raw file for {dataset} {year} in {folder}. "
        f"Tried: {cfg['data']['filename_patterns'][dataset]}"
    )


def raw_files(dataset: str, years: Optional[Iterable[int]] = None) -> Dict[int, Path]:
    """Map year -> raw CSV path for one dataset."""
    cfg = load_config()
    return {y: raw_file(dataset, y) for y in (years or cfg["data"]["years"])}


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def read_raw_sql(dataset: str, year: int) -> str:
    """Build the DuckDB read_csv(...) expression for one raw file.

    Returns a SQL fragment you drop into a FROM clause. Column types are given
    explicitly so that an all-NULL column does not get sniffed as text.

        con.execute(f"SELECT count(*) FROM {read_raw_sql('flood', 2019)}")
    """
    cfg = load_config()
    schema = cfg["data"]["schema"][dataset]
    path = raw_file(dataset, year)
    types = ", ".join(f"'{col}': 'DOUBLE'" for col in schema["values"])
    return (
        f"read_csv('{path}', header=true, "
        f"nullstr='{cfg['data']['null_token']}', "
        f"sample_size=300000, types={{{types}}})"
    )


def _range_check_sql(dataset: str, column: str) -> str:
    """Wrap a value column so out-of-range readings become NULL.

    We null implausible values rather than clipping them: a 762 mm/24h reading
    is not a big rainfall, it is a broken record, and clipping it to 400 would
    invent a storm that never happened.
    """
    checks = load_config()["exclusions"].get("range_checks", {}).get(dataset, {})
    rule = checks.get(column)
    if not rule:
        return column
    lo, hi = rule["min"], rule["max"]
    return f"CASE WHEN {column} BETWEEN {lo} AND {hi} THEN {column} END"


# ---------------------------------------------------------------------------
# Writing Parquet
# ---------------------------------------------------------------------------
def interim_path(dataset: str, year: int) -> Path:
    """Where the cleaned Parquet for one dataset-year lives."""
    return resolve(load_config()["paths"]["interim"]) / f"{dataset}_{year}.parquet"


def manifest_path(dataset: str, year: int) -> Path:
    """Where the provenance record for one cleaned file lives.

    Every Parquet file gets a small JSON sidecar saying what produced it: how
    many rows, how many values the range checks removed, which config version
    was in force, and when. Without it, "was this file built before or after we
    changed the rainfall ceiling?" is unanswerable.
    """
    folder = resolve(load_config()["paths"]["interim"]) / "_manifest"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{dataset}_{year}.json"


def ingest_year_to_parquet(
    dataset: str,
    year: int,
    con=None,
    overwrite: bool = False,
) -> Dict[str, object]:
    """Clean one raw CSV and write it as Parquet. Returns a small report.

    What "clean" means here, and nothing more:
      * BOM handled, NULL -> missing, quoted Thai names parsed correctly
      * value columns typed as DOUBLE
      * implausible values nulled and *counted* (never silently dropped)
      * columns renamed to a common shape: station_code, ts, then the values
      * the station name kept, because it is the only human-readable label we
        have for most sensors

    Note what it does NOT do: it does not drop excluded stations. FW.PKG.01 is
    excluded from *canal averages*, not from the archive — it is a real Chao
    Phraya gauge and we will want it later. Exclusions belong in feature
    building, not in ingestion.
    """
    cfg = load_config()
    schema = cfg["data"]["schema"][dataset]
    out = interim_path(dataset, year)
    out.parent.mkdir(parents=True, exist_ok=True)

    owns_connection = con is None
    con = con or connect()
    try:
        mf = manifest_path(dataset, year)
        if out.exists() and not overwrite:
            if mf.exists():
                record = json.loads(mf.read_text())
                record["skipped"] = True
                return record
            # Parquet present but no provenance record — rebuild rather than
            # trust a file we cannot account for.
            overwrite = True

        src = read_raw_sql(dataset, year)
        ts = cfg["data"]["timestamp_column"]

        # How many readings each range check will remove. Computed before the
        # write so the number can go straight into the quality scorecard.
        flagged = {}
        for col in schema["values"]:
            checked = _range_check_sql(dataset, col)
            if checked == col:
                continue
            flagged[col] = con.execute(
                f"SELECT count(*) FROM {src} "
                f"WHERE {col} IS NOT NULL AND ({checked}) IS NULL"
            ).fetchone()[0]

        value_sql = ", ".join(
            f"({_range_check_sql(dataset, col)})::DOUBLE AS {col}"
            for col in schema["values"]
        )
        select = (
            f"SELECT {schema['code']} AS station_code, "
            f"{schema['name']} AS station_name, "
            f"{ts}::TIMESTAMP AS ts, {value_sql} "
            f"FROM {src}"
        )
        compression = cfg["compute"]["parquet_compression"].upper()
        con.execute(
            f"COPY ({select}) TO '{out}' "
            f"(FORMAT PARQUET, COMPRESSION {compression})"
        )
        rows = con.execute(f"SELECT count(*) FROM read_parquet('{out}')").fetchone()[0]
        record = {
            "dataset": dataset,
            "year": year,
            "rows": int(rows),
            "range_flagged": flagged,
            "bytes": out.stat().st_size,
            "source_file": raw_file(dataset, year).name,
            "source_bytes": raw_file(dataset, year).stat().st_size,
            "config_version": cfg["version"],
            "built_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        manifest_path(dataset, year).write_text(json.dumps(record, indent=2))
        record["skipped"] = False
        return record
    finally:
        if owns_connection:
            con.close()


def verify_ordering(dataset: str, year: int, con=None) -> Dict[str, object]:
    """Check that a cleaned Parquet really is sorted by station then time.

    Ingestion skips the sort because the raw files already arrive ordered.
    That is an assumption about a supplier's export process, so it gets
    checked rather than believed. Cheap: one pass, no sort.
    """
    owns = con is None
    con = con or connect()
    try:
        src = f"read_parquet('{interim_path(dataset, year)}')"
        bad = con.execute(
            f"""
            SELECT count(*) FROM (
                SELECT station_code, ts,
                       lag(station_code) OVER () AS prev_code,
                       lag(ts)           OVER () AS prev_ts
                FROM {src}
            )
            WHERE prev_code IS NOT NULL
              AND (station_code < prev_code
                   OR (station_code = prev_code AND ts <= prev_ts))
            """
        ).fetchone()[0]
    finally:
        if owns:
            con.close()
    return {"dataset": dataset, "year": year, "out_of_order_rows": int(bad),
            "ordered": bad == 0}


def interim_sql(dataset: str, years: Optional[Iterable[int]] = None) -> str:
    """Build a read_parquet(...) expression over one or more cleaned years.

        con.execute(f"SELECT count(*) FROM {interim_sql('flood')}")
    """
    cfg = load_config()
    paths = [str(interim_path(dataset, y)) for y in (years or cfg["data"]["years"])]
    missing = [p for p in paths if not Path(p).exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing cleaned Parquet: {missing[:3]}{'...' if len(missing) > 3 else ''}. "
            "Run notebook 01 first."
        )
    listed = ", ".join(f"'{p}'" for p in paths)
    return f"read_parquet([{listed}])"
