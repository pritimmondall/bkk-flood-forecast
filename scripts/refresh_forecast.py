#!/usr/bin/env python3
"""
Refresh the archived forecast rainfall, and nothing else.

    python scripts/refresh_forecast.py

Seven API calls, about two minutes. Writes
`data/external/openmeteo_forecast_rain.parquet` and verifies it.

WHY THIS EXISTS RATHER THAN "RE-RUN NOTEBOOK 04". The forecast model changed
(ECMWF splice -> GFS) and only that one file needs rebuilding. ERA5 and Traffy
Fondue are unaffected and already on disk, so re-running the whole notebook would
re-do a lot of work to change one thing.

DO NOT DELETE THE CACHE FIRST. Earlier advice in this project said to
`rm data/external/_cache/forecast_*` before switching models. That was correct
when the cache key was `forecast_<year>_...`, and became wrong once the key
started including the model name: `forecast_gfs_seamless_2021_...` cannot
collide with `forecast_ecmwf_ifs04_2021_...`. Deleting would throw away good
ECMWF responses for no reason and force a needless re-fetch.

The guard runs at the end and fails loudly on either of the two ways this has
gone wrong before: a reanalysis wearing a forecast's filename, and an empty file
wearing a plausible row count.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from bkkflood.config import load_config  # noqa: E402
from bkkflood.external import (  # noqa: E402
    assert_forecast_is_not_reanalysis,
    fetch_forecast_rain,
)


def main() -> int:
    cfg = load_config()
    source = cfg["external"]["open_meteo"]["forecast"]
    out = Path(source["out"])

    print("Refreshing archived forecast rainfall")
    print(f"  models : {source['models']}")
    print(f"  years  : {cfg['data']['years']}")
    print(f"  output : {out}")
    print()

    before = len(pd.read_parquet(out)) if out.exists() else 0

    df = fetch_forecast_rain()
    if df.empty:
        raise SystemExit(
            "\nNothing was retrieved. Check connectivity to "
            "historical-forecast-api.open-meteo.com, then try again — "
            "anything already cached is reused, so a retry is cheap."
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)

    df["year"] = pd.to_datetime(df.ts).dt.year
    per_year = df.groupby("year")["fcst_precipitation"].agg(rows="size", filled="count")

    print()
    print("Coverage by year")
    print(per_year.to_string())
    print()
    print(f"  rows written : {len(df):,}   (previously {before:,})")

    # ---- Verify, do not assume. Both failure modes are silent. ----
    print()
    try:
        report = assert_forecast_is_not_reanalysis()
    except ValueError as exc:
        print("GUARD FAILED — do not build features on this file:")
        print(exc)
        return 1

    print("GUARD PASSED")
    print(f"  usable years  : {report['usable_years']}")
    print(f"  usable rows   : {report['usable_row_share']:.1%}")
    print()
    print(f"{'year':<6}{'identical(all)':>16}{'identical(wet)':>16}{'wet hours':>12}")
    for year, r in sorted(report["by_year"].items()):
        print(f"{year:<6}{r['identical_all']:>15.1%}{r['identical_wet']:>16.1%}"
              f"{r['wet_hours']:>12,}")
    print()
    print("  Low agreement on wet hours is what a real forecast looks like: right")
    print("  about roughly when it rains, wrong about exactly how much.")
    print()
    print("Done. Nothing else needs re-running — Phase 3 is next.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
