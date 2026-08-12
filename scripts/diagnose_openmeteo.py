#!/usr/bin/env python3
"""
Which Open-Meteo model gives a REAL archived forecast, and from when.

    python scripts/diagnose_openmeteo.py

The first version of this script asked the wrong question. It asked "does the
endpoint return data?" — every candidate said yes, so `model: null` was chosen
for its apparently full 2019-2025 coverage.

It returned ERA5. All seven years of "archived forecast" matched the reanalysis
file value for value, correlation 1.0000. Without an explicit model, the
historical-forecast endpoint serves archived analysis for past dates rather than
what the model actually predicted at the time.

The right question is not "did data come back" but **"is it different from what
actually fell"**. A forecast that equals the observation is not a forecast, it
is the answer sheet — and it would train beautifully and fail on the first live
day with no error anywhere.

So this script fetches BOTH endpoints for the same window and reports the share
of hours where they are identical. Anything near 100% is contaminated.

It then got caught a second time, the other way round. `ecmwf_ifs025` was picked
because it looked "genuinely different" back to 2019 -- but its archive starts in
February 2024, so the earlier years came back empty, and NaN is not equal to
anything either. 73% of the pulled file was blank. Absence read as difference.

So there are now THREE outcomes per year, not two:

    NO DATA        the archive does not reach that year
    REANALYSIS     it reaches it, but the values are what actually fell
    real forecast  it reaches it, and the values are a genuine prediction

Only the third is usable. Takes about two minutes.
"""

from __future__ import annotations

import sys
import time

import requests

FORECAST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"   # ERA5, what actually fell

# Bangkok, roughly the middle.
BASE = {
    "latitude": 13.7563,
    "longitude": 100.5018,
    "hourly": "precipitation,rain",
    "timezone": "Asia/Bangkok",
}

# The names worth trying. `None` means "send no models parameter at all",
# which is what the working ERA5 call does.
CANDIDATES = [
    None,
    "ecmwf_ifs_hres",     # what config.yaml had. Invalid slug, kept as a guard.
    "ecmwf_ifs025",       # 0.25 deg (~25 km), archived 2024-02
    "ecmwf_ifs04",        # 0.4 deg (~44 km), archived 2022-11
    "best_match",
    # --- GFS, suggested by the supervisor -------------------------------
    # NOAA/NCEP's global model. The supervisor's note gives 0.25 deg (~25-28 km),
    # which is what NOAA publishes. Open-Meteo's own model table lists GFS
    # surface variables at 0.11 deg (~13 km) and archived from 2021-03-23 --
    # potentially both FINER than ECMWF IFS 0.25 and reaching 20 months further
    # back than ifs04. Both claims are worth measuring rather than believing.
    "gfs_seamless",
    "gfs_global",
]

# Probe years chosen to find where each archive begins, not just whether it works.
PROBE_YEARS = (2019, 2021, 2022, 2023, 2024, 2025)


def probe(model, start, end, timeout=30):
    params = dict(BASE, start_date=start, end_date=end)
    if model:
        params["models"] = model
    try:
        r = requests.get(FORECAST_URL, params=params, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        return None, f"connection error: {exc}"
    if r.status_code != 200:
        try:
            reason = r.json().get("reason", r.text[:160])
        except Exception:  # noqa: BLE001
            reason = r.text[:160]
        return None, f"HTTP {r.status_code}: {reason}"
    hourly = r.json().get("hourly", {})
    values = hourly.get("precipitation") or []
    real = [v for v in values if v is not None]
    return len(real), f"{len(values)} hours, {len(real)} with a value"


def series(url, model, start, end):
    """Return the hourly precipitation list, or None."""
    params = dict(BASE, start_date=start, end_date=end)
    if model:
        params["models"] = model
    try:
        r = requests.get(url, params=params, timeout=60)
        if r.status_code != 200:
            return None
        return r.json().get("hourly", {}).get("precipitation")
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    print("=" * 72)
    print("1. WHICH MODEL NAME DOES THE API ACCEPT?")
    print("   (two days in June 2024 — well inside any coverage window)")
    print("=" * 72)
    working = []
    for model in CANDIDATES:
        label = model or "(no models parameter)"
        n, msg = probe(model, "2024-06-01", "2024-06-02")
        status = "OK  " if n else "FAIL"
        print(f"  {status} {label:<28} {msg}")
        if n:
            working.append(model)
        time.sleep(1.0)

    if not working:
        print("\n  Nothing worked. That points at connectivity rather than the")
        print("  model name — check that historical-forecast-api.open-meteo.com")
        print("  is reachable from this machine (ERA5 uses a different host).")
        return 1

    print()
    print("=" * 72)
    print("2. IS IT ACTUALLY A FORECAST, OR JUST THE REANALYSIS?")
    print("   Fetching the SAME window from the archive endpoint and comparing.")
    print("   Identical values mean the 'forecast' is what actually fell.")
    print()
    print("   Read the WET column, not the ALL column. 78% of hours in this")
    print("   archive have no rain, so any two sources agree most of the time")
    print("   simply by both saying dry. Only agreement on wet hours is")
    print("   informative -- a real forecast disagrees there constantly.")
    print("=" * 72)

    results = {}
    for model in working:
        label = model or "(no models parameter)"
        print(f"\n  {label}")
        usable = []
        for year in PROBE_YEARS:
            fc = series(FORECAST_URL, model, f"{year}-06-01", f"{year}-06-07")
            ob = series(ARCHIVE_URL, None, f"{year}-06-01", f"{year}-06-07")
            if fc is None or ob is None:
                print(f"    {year}   no data")
                continue
            n = min(len(fc), len(ob))
            pairs = list(zip(fc[:n], ob[:n]))

            # THREE states, not two. The previous version had two, and that cost
            # a whole round trip: `null` returned NaN for years outside its
            # archive, NaN never equals anything, so "0% identical" was scored as
            # "genuinely different" when it actually meant "nothing came back".
            # Absence looked exactly like difference.
            present = [(a, b) for a, b in pairs if a is not None]
            if len(present) < 0.5 * max(n, 1):
                print(f"    {year}   NO DATA ({len(present)}/{n} hours returned)"
                      f"   archive does not reach this year")
                time.sleep(0.8)
                continue

            same = sum(1 for a, b in present if a == b) / len(present)
            wet = [(a, b) for a, b in present if (a or 0) > 0 or (b or 0) > 0]
            wet_same = (sum(1 for a, b in wet if a == b) / len(wet)) if wet else 0.0
            # Rainfall is mostly zero -- about 75% of hours in this archive are
            # dry -- so two sources agree on most hours just by both saying "no
            # rain". Agreement on WET hours is the measure that carries
            # information: a real forecast disagrees there constantly.
            bad = same > 0.99 or (len(wet) > 20 and wet_same > 0.95)
            verdict = "REANALYSIS - unusable" if bad else "real forecast"
            if not bad:
                usable.append(year)
            print(f"    {year}   all {100 * same:5.1f}%   "
                  f"wet {100 * wet_same:5.1f}% of {len(wet):>3} wet hours   {verdict}")
            time.sleep(0.8)
        results[label] = usable

    print()
    print("=" * 72)
    good = {k: v for k, v in results.items() if v}
    if not good:
        print("  NONE of the candidates returns a genuine archived forecast for")
        print("  the years probed. Leave rain_fcst_* out of the feature set and")
        print("  say so: the BMA gauges remain the primary rainfall input, and a")
        print("  missing feature is safe where a disguised reanalysis is not.")
    else:
        label, years = max(good.items(), key=lambda kv: len(kv[1]))
        print("  Genuine forecast years, by model:")
        for k, v in sorted(good.items(), key=lambda kv: -len(kv[1])):
            print(f"    {k:<28} {v}")
        print()
        print(f"  Widest genuine coverage: {label} -> {years}")
        print()
        print("  Pick on COVERAGE first. rain_fcst_* is only useful in the folds")
        print("  where it exists, and this project has 837 events total. A model")
        print("  present in one fold and absent in three is a feature whose")
        print("  importance cannot be compared across folds.")
        print()
        print("  Then: clear data/external/_cache/forecast_* and re-pull, or the")
        print("  contaminated responses will be served straight back from cache.")
        print("  Notebook 05 must call assert_forecast_is_not_reanalysis() before")
        print("  using rain_fcst_* for anything.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
