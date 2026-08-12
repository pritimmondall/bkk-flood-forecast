"""
Fetching data we do not own: rainfall from Open-Meteo, flood reports from
Traffy Fondue.

--------------------------------------------------------------------------
THE ONE THING TO UNDERSTAND BEFORE USING THIS MODULE
--------------------------------------------------------------------------
Open-Meteo publishes two rainfall archives. They return the same fields in the
same shape, and confusing them will produce a model that scores beautifully in
testing and fails on its first live day.

    fetch_forecast_rain()   historical-forecast-api
                            What the weather model PREDICTED at the time.
                            Built by stitching together the first hours of each
                            successive model run, so a value at 14:00 comes from
                            a run launched a few hours earlier.
                            -> legitimate as a forecast feature.

    fetch_era5_rain()       archive-api (ERA5 reanalysis)
                            What actually FELL, reconstructed afterwards using
                            observations that did not exist at forecast time.
                            -> legitimate as a past-rain feature.
                            -> NEVER legitimate as a forecast feature.

Why it matters so much here: rainfall carries roughly three quarters of the
forecasting signal in this project. If ERA5 is used as `rain_fcst_3h`, the model
is being trained on the answer sheet. At serving time it would get a real
forecast instead — a much weaker input — and its accuracy would fall off a cliff
with no error raised anywhere.

The two functions therefore write to different files and their columns carry
different prefixes (`fcst_` vs `era5_`). Notebook 05 must never mix them.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd

from .config import load_config, resolve

try:  # requests is the only hard dependency added by Phase 2
    import requests
except ImportError:  # pragma: no cover
    requests = None


# ---------------------------------------------------------------------------
# Where to pull for
# ---------------------------------------------------------------------------
def district_points(refresh: bool = False) -> pd.DataFrame:
    """The 50 Bangkok district centroids, as the points we request weather for.

    Returns: district, lon, lat.

    Why district centroids and not sensor positions? Two reasons. The sensor
    "positions" we hold *are* district centroids (notebook 00, §B.8), so there
    would be nothing to gain. And rainfall is already joined to flood sites by
    district everywhere else in this project, so one key stays consistent.

    A caveat that must travel with this table: IFS HRES is ~9 km and ERA5 ~25 km,
    while Bangkok is about 40 km across. Several districts will resolve to the
    same grid cell. These are *regional* rainfall series labelled by district,
    not district-specific measurements.
    """
    cfg = load_config()
    cache = resolve(cfg["external"]["points_cache"])
    if cache.exists() and not refresh:
        return pd.read_csv(cache)

    geo = json.loads(resolve(cfg["paths"]["districts"]).read_text(encoding="utf-8"))
    rows = []
    for feature in geo["features"]:
        xs: List[float] = []
        ys: List[float] = []

        def walk(coords):
            if isinstance(coords[0], (int, float)):
                xs.append(coords[0])
                ys.append(coords[1])
            else:
                for part in coords:
                    walk(part)

        walk(feature["geometry"]["coordinates"])
        # Mean of the vertices. Crude next to a true polygon centroid, but these
        # points only select a ~9 km weather grid cell — the difference is far
        # below the resolution of the thing being selected.
        rows.append({
            "district": feature["properties"]["name"],
            "lon": round(sum(xs) / len(xs), 5),
            "lat": round(sum(ys) / len(ys), 5),
        })

    df = pd.DataFrame(rows).sort_values("district").reset_index(drop=True)
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache, index=False)
    return df


# ---------------------------------------------------------------------------
# A polite, resumable HTTP helper
# ---------------------------------------------------------------------------
def _cache_path(name: str) -> Path:
    cfg = load_config()["external"]["open_meteo"]["request"]
    folder = resolve(cfg["cache_dir"])
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{name}.json"


def _get_json(url: str, params: Dict, cache_key: Optional[str] = None) -> Dict:
    """GET with caching, retries and a pause between calls.

    Every response is cached to disk. That is not an optimisation — it is what
    makes a 100-call pull resumable, and it means re-running a notebook does not
    re-hammer somebody else's free service.
    """
    if requests is None:
        raise ImportError("requests is not installed. pip install -r requirements.txt")

    rq = load_config()["external"]["open_meteo"]["request"]

    if cache_key:
        cached = _cache_path(cache_key)
        if cached.exists():
            return json.loads(cached.read_text())

    last_error = None
    for attempt in range(rq["max_retries"]):
        try:
            response = requests.get(url, params=params, timeout=rq["timeout_seconds"])
            if response.status_code == 429:
                # Rate limited. Wait longer each time rather than retrying hard.
                time.sleep(rq["backoff_seconds"] * (attempt + 2))
                continue
            response.raise_for_status()
            payload = response.json()
            if cache_key:
                _cache_path(cache_key).write_text(json.dumps(payload))
            time.sleep(rq["seconds_between_calls"])
            return payload
        except Exception as exc:  # noqa: BLE001 - we want to retry on anything
            last_error = exc
            time.sleep(rq["backoff_seconds"] * (attempt + 1))
    raise RuntimeError(f"Failed after {rq['max_retries']} attempts: {url} :: {last_error}")


# ---------------------------------------------------------------------------
# Open-Meteo
# ---------------------------------------------------------------------------
def _normalise_response(payload) -> List[Dict]:
    """Open-Meteo returns an object for one coordinate and a list for many.

    Normalise both to a list, in the same order the coordinates were sent.
    """
    if isinstance(payload, list):
        return payload
    return [payload]


def _fetch_openmeteo(
    which: str,
    points: Optional[pd.DataFrame] = None,
    years: Optional[Iterable[int]] = None,
    prefix: str = "",
    batch_size: Optional[int] = None,
    progress: bool = True,
) -> pd.DataFrame:
    """Shared body for the two Open-Meteo pulls. Use the wrappers below.

    Two deliberate choices about how we ask:

    *Batched coordinates.* Open-Meteo accepts comma-separated latitudes and
    longitudes and returns one result per point. Asking for all 50 districts in
    a single request turns 350 calls into 7 — better for us and considerably
    better for a free service we do not pay for.

    *Chunked by year.* A seven-year hourly request for 50 points is a large
    response and some endpoints refuse long ranges. Year chunks keep each
    response manageable and make the pull resumable at a sensible granularity:
    if it stops half way, re-running skips everything already cached.
    """
    cfg = load_config()
    om = cfg["external"]["open_meteo"]
    source = om[which]
    points = (district_points() if points is None else points).reset_index(drop=True)
    years = list(years or cfg["data"]["years"])
    batch_size = batch_size or om["request"].get("batch_size", 25)

    # SEVERAL MODELS, SPLICED. ECMWF's archives are complementary rather than
    # competing: IFS 0.4 degrees runs from 2022-11 to about 2024-02, when IFS
    # 0.25 degrees takes over. Neither alone covers much of our seven years;
    # together they cover roughly three. Later models win where both have data,
    # since they are the finer grid.
    #
    # The splice is a real compromise -- the grid changes from ~44 km to ~25 km
    # part way through the series -- but it is a KNOWN and dated change, which
    # is the difference between a documented regime shift and best_match
    # silently swapping models underneath you.
    # Preference order, most-preferred LAST. See config for the measurement
    # behind the current choice.
    models = source.get("models") or [source.get("model")]
    if isinstance(models, str):
        models = [models]

    frames = []
    for model in models:
        for year in years:
            for start_idx in range(0, len(points), batch_size):
                chunk = points.iloc[start_idx:start_idx + batch_size]
                params = {
                    "latitude": ",".join(str(v) for v in chunk.lat),
                    "longitude": ",".join(str(v) for v in chunk.lon),
                    "start_date": f"{year}-01-01",
                    "end_date": f"{year}-12-31",
                    "hourly": ",".join(om["hourly"]),
                    "timezone": om["timezone"],
                }
                if model:
                    params["models"] = model

                # The model goes in the key only when there IS one. Adding a
                # "_default" segment for the no-model (ERA5) source renamed
                # every existing cache entry, orphaned 3 million already-fetched
                # rows, and forced a re-pull that came back two years short --
                # silently, because the row count still looked plausible.
                # A cache key change is a data migration. Treat it as one.
                key = "_".join(filter(None, [which, model, str(year),
                                             str(start_idx), str(len(chunk))]))
                try:
                    payload = _get_json(source["url"], params, cache_key=key)
                except Exception as exc:  # noqa: BLE001
                    # Report and continue. A year the archive does not cover is a
                    # finding, not a crash — and everything already fetched is kept.
                    if progress:
                        print(f"  {year}  points {start_idx}-{start_idx + len(chunk) - 1}"
                              f"  FAILED: {str(exc)[:120]}", flush=True)
                    continue

                results = _normalise_response(payload)
                if len(results) != len(chunk):
                    if progress:
                        print(f"  {year}  expected {len(chunk)} results, got {len(results)}"
                              f" - matching by position may be wrong, skipping batch",
                              flush=True)
                    continue

                got_hours = 0
                for result, (_, row) in zip(results, chunk.iterrows()):
                    hourly = (result or {}).get("hourly") or {}
                    if not hourly.get("time"):
                        continue
                    df = pd.DataFrame(hourly)
                    df["ts"] = pd.to_datetime(df.pop("time"))
                    df.insert(0, "district", row.district)
                    df = df.rename(columns={c: f"{prefix}{c}" for c in df.columns
                                            if c not in ("district", "ts")})
                    frames.append(df)
                    got_hours += len(df)

                if progress:
                    print(f"  {model or 'default'} {year}  points {start_idx:>2}-{start_idx + len(chunk) - 1:<2}"
                          f"  {got_hours:>8,} hours returned", flush=True)

    if not frames:
        return pd.DataFrame(columns=["district", "ts"])

    # DROP EMPTY ROWS PER FRAME, BEFORE CONCATENATING AND BEFORE DEDUPING.
    # The order matters, and getting it wrong cost a round trip.
    #
    # A model returns a full-length response for years outside its archive, with
    # every value null. Concatenating those and then keeping the last row per
    # (district, ts) discards real data: ecmwf_ifs04 covers 2023 in full and
    # ecmwf_ifs025 does not, so "later model wins" replaced 8,760 genuine hours
    # per district with the newer model's NaNs. The API had returned the data.
    # The splice threw it away, and the row count still looked plausible.
    cleaned = []
    for d in frames:
        value_cols = [c for c in d.columns if c not in ("district", "ts")]
        d = d.dropna(subset=value_cols, how="all").copy()
        if len(d):
            # Pin the dtype. A variable that is null for a whole year (Open-Meteo
            # returns `rain` as null in some responses while `precipitation` has
            # values) leaves an all-NA column, and pandas warns that its dtype
            # inference for those is changing. Declaring float64 makes the
            # concatenation unambiguous instead of relying on inference.
            d[value_cols] = d[value_cols].astype("float64")
            cleaned.append(d)
    if not cleaned:
        return pd.DataFrame(columns=["district", "ts"])

    # Last entry in `models` wins where several have data. The list is a
    # PREFERENCE order, not a chronological one -- an earlier version of this
    # comment justified it as "later = finer grid", which stopped being true the
    # moment GFS (0.11 deg) joined a list whose later entries were ECMWF IFS
    # 0.25 and 0.4. Put the model you most want last.
    return (pd.concat(cleaned, ignore_index=True)
              .drop_duplicates(subset=["district", "ts"], keep="last")
              .sort_values(["district", "ts"])
              .reset_index(drop=True))


def fetch_forecast_rain(**kwargs) -> pd.DataFrame:
    """Archived FORECAST rainfall — what the model said at the time.

    Safe to use as `rain_fcst_*`. Columns are prefixed `fcst_`.

    Coverage is the open question: Open-Meteo documents ECMWF IFS HRES as
    archived from 2017, which would span all seven of our years, but that is a
    claim in a table rather than something we have seen. `coverage_report()`
    below checks it against what actually came back, per year.
    """
    return _fetch_openmeteo("forecast", prefix="fcst_", **kwargs)


def fetch_era5_rain(**kwargs) -> pd.DataFrame:
    """ERA5 reanalysis rainfall — what actually fell.

    Safe as a PAST-rain feature (`era5_*`). **Never** safe as a forecast: it is
    reconstructed after the fact from observations that did not exist at
    forecast time. Columns are prefixed `era5_` so the mistake is hard to make
    by accident.
    """
    return _fetch_openmeteo("observed", prefix="era5_", **kwargs)


def coverage_report(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    """Per year: how many hours came back, and how many carry a real value.

    Run this before believing any coverage claim from documentation.
    """
    if df.empty:
        return pd.DataFrame(columns=["year", "districts", "hours", "hours_with_value",
                                     "coverage_pct"])
    out = df.copy()
    out["year"] = out["ts"].dt.year
    g = (out.groupby("year")
           .agg(districts=("district", "nunique"),
                hours=("ts", "size"),
                hours_with_value=(value_col, "count"))
           .reset_index())
    g["coverage_pct"] = (100 * g.hours_with_value / g.hours).round(2)
    return g


# ---------------------------------------------------------------------------
# Traffy Fondue
# ---------------------------------------------------------------------------
def fetch_traffy(max_pages: Optional[int] = None, progress: bool = True) -> pd.DataFrame:
    """Citizen problem reports with coordinates, from the public GeoJSON API.

    Returns a flat table: ticket_id, ts, lon, lat, district, subdistrict,
    problem types, description, state, photo_url.

    **What this is for.** Our flood labels come from 107 sensors. A road that
    floods where there is no sensor did not flood, as far as the model and the
    evaluation are concerned — and nobody has ever been able to say how much
    that misses. These reports are the first independent measurement of it.

    Use them for evaluation before considering them for training. A report means
    "a person complained", not "the depth was 15 cm", and reporting is biased
    towards populated, connected, smartphone-carrying areas.

    The endpoint is paginated and live. Historical depth is unknown and is
    measured, not assumed, in notebook 04 — a bulk archive may need a request to
    NECTEC.
    """
    cfg = load_config()["external"]["traffy_fondue"]
    page_size = cfg["page_size"]
    max_pages = max_pages or cfg["max_pages"]

    rows: List[Dict] = []
    seen = set()
    for page in range(max_pages):
        offset = page * page_size
        payload = _get_json(cfg["url"],
                            {"limit": page_size, "offset": offset},
                            cache_key=f"traffy_{offset}_{page_size}")
        features = payload.get("features") or []
        if not features:
            break

        new = 0
        for feature in features:
            props = feature.get("properties") or {}
            ticket = props.get("ticket_id")
            if ticket in seen:
                continue
            seen.add(ticket)
            new += 1
            coords = (feature.get("geometry") or {}).get("coordinates") or [None, None]
            rows.append({
                "ticket_id": ticket,
                "ts": props.get("timestamp"),
                "lon": coords[0],
                "lat": coords[1],
                "district": props.get("district"),
                "subdistrict": props.get("subdistrict"),
                "province": props.get("province"),
                "problem_types": "|".join(props.get("problem_type_fondue") or []),
                "description": props.get("description"),
                "state": props.get("state"),
                "photo_url": props.get("photo_url"),
            })

        if progress:
            print(f"  page {page + 1:>3}  offset {offset:>7,}  "
                  f"+{new:>5,} new  (total {len(rows):,})", flush=True)
        if new == 0:
            # The API is returning things we already have — stop rather than
            # spin through 200 pages of duplicates.
            break

    df = pd.DataFrame(rows)
    if not df.empty:
        df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
    return df


def is_flood_report(df: pd.DataFrame) -> pd.Series:
    """Flag the reports that are about flooding.

    Matches the Thai category text (`น้ำท่วม` = flood, `ท่อระบายน้ำ` = drain)
    in both the category list and the free-text description. Keyword matching on
    user-written Thai is approximate by nature — it will miss reports that
    describe flooding without naming it, and catch some that merely mention a
    drain. Treat the count as a lower bound.
    """
    keywords = load_config()["external"]["traffy_fondue"]["flood_keywords"]
    haystack = (df.get("problem_types", "").fillna("") + " "
                + df.get("description", "").fillna(""))
    mask = pd.Series(False, index=df.index)
    for word in keywords:
        mask |= haystack.str.contains(word, case=False, na=False, regex=False)
    return mask


# ---------------------------------------------------------------------------
# The guard that should have existed from the start
# ---------------------------------------------------------------------------
def assert_forecast_is_not_reanalysis(
    forecast: Optional[pd.DataFrame] = None,
    observed: Optional[pd.DataFrame] = None,
    max_identical_all: float = 0.99,
    max_identical_wet: float = 0.95,
) -> Dict[str, object]:
    """Fail loudly if the 'forecast' file is really ERA5 under another name.

    WHY THIS EXISTS. On 2026-08-08 the archived-forecast pull was fixed by
    removing an invalid `models` value from config. It then returned 3,068,400
    rows across all seven years and looked completely healthy. It was ERA5 --
    every value identical to the reanalysis file, correlation 1.0000, in all
    seven years. Without an explicit model the historical-forecast endpoint
    serves archived *analysis* for past dates, not what was predicted at the
    time. Different hosts, different filenames, different column prefixes, same
    numbers.

    That is the failure rule 7 exists to prevent, and the `fcst_` / `era5_`
    prefix scheme did not catch it, because prefixes separate *names* and the
    problem was *content*.

    TWO MEASURES, BECAUSE RAINFALL IS MOSTLY ZERO. 78% of hours in this archive
    have no rain at all, so a forecast and an observation agree on most hours
    simply by both saying "dry". A raw identical-share of 60-70% is the dry-hour
    baseline, not evidence of anything. The number that carries information is
    agreement on **wet** hours -- those where either source reports rain. A real
    forecast disagrees with the observation constantly on wet hours; a copy does
    not.

    Raises if the two look like the same data. Returns a per-year report if not.
    """
    cfg = load_config()
    om = cfg["external"]["open_meteo"]
    if forecast is None:
        forecast = pd.read_parquet(resolve(om["forecast"]["out"]))
    if observed is None:
        observed = pd.read_parquet(resolve(om["observed"]["out"]))

    merged = forecast.merge(observed, on=["district", "ts"], how="inner")
    if merged.empty:
        raise ValueError("forecast and observed rainfall do not overlap at all")

    merged["year"] = pd.to_datetime(merged["ts"]).dt.year

    # ---- Check 0: is there any forecast at all? -------------------------
    # This check exists because the guard passed a file that was 73% empty.
    # `ecmwf_ifs025` only reaches back to 2024-02, so 2019-2023 came back as
    # all-NaN. NaN never equals anything, so "identical share" was 0.0% and the
    # contamination test read that as a clean bill of health. Absence looked
    # exactly like difference.
    #
    # An empty feature is not as dangerous as a leaked one, but it is still a
    # silent lie: the row count looks right, the file loads, and the model
    # quietly receives nothing for its most valuable long-range input.
    coverage = (merged.groupby("year")["fcst_precipitation"]
                .apply(lambda c: round(float(c.notna().mean()), 4)).to_dict())
    empty_years = sorted(int(y) for y, share in coverage.items() if share < 0.01)

    f, o = merged["fcst_precipitation"], merged["era5_precipitation"]
    merged["_same"] = f == o
    merged["_wet"] = (f > 0) | (o > 0)

    per_year, contaminated = {}, []
    for year, grp in merged.groupby("year"):
        wet = grp[grp["_wet"]]
        rec = {
            "identical_all": round(float(grp["_same"].mean()), 4),
            "identical_wet": (round(float(wet["_same"].mean()), 4)
                              if len(wet) else float("nan")),
            "wet_hours": int(len(wet)),
            "corr": (round(float(grp["fcst_precipitation"]
                                 .corr(grp["era5_precipitation"])), 4)
                     if len(grp) > 2 else float("nan")),
        }
        per_year[int(year)] = rec
        if (rec["identical_all"] > max_identical_all
                or (rec["wet_hours"] > 100 and rec["identical_wet"] > max_identical_wet)):
            contaminated.append(int(year))

    report = {
        "by_year": per_year,
        "coverage_by_year": {int(y): v for y, v in coverage.items()},
        "empty_years": empty_years,
        "contaminated_years": sorted(contaminated),
        "usable_years": sorted(int(y) for y in per_year
                               if y not in contaminated and y not in empty_years),
        "dry_hour_share": round(float((~merged["_wet"]).mean()), 4),
        "usable_row_share": round(float(f.notna().mean()), 4),
        "passed": not contaminated and not empty_years,
    }
    if empty_years:
        detail = "  ".join(f"{y}:{100 * s:.0f}%" for y, s in sorted(coverage.items()))
        raise ValueError(
            f"rain_fcst_* has NO DATA for {empty_years}. Only "
            f"{100 * report['usable_row_share']:.0f}% of rows carry a forecast.\n"
            "  The archived-forecast endpoint does not reach that far back for "
            "the configured model. Choose a model whose archive actually covers "
            "the training years (run scripts/diagnose_openmeteo.py, which now "
            "separates 'no data' from 'genuinely different'), or accept the gap "
            "deliberately and record in notebook 05 that rain_fcst_* exists for "
            "only part of the rolling-origin folds.\n"
            f"  coverage by year: {detail}"
        )
    if contaminated:
        detail = "\n".join(
            f"    {y}: {r['identical_all']:.1%} of all hours identical, "
            f"{r['identical_wet']:.1%} of {r['wet_hours']:,} wet hours, corr {r['corr']}"
            for y, r in sorted(per_year.items())
        )
        raise ValueError(
            "rain_fcst_* is not a forecast for "
            f"{sorted(contaminated)}: it matches the ERA5 reanalysis too "
            "closely to be a prediction. Using it as a forecast feature would "
            "train the model on the answer sheet.\n"
            "  Fix: pin an explicit model in config "
            "(external.open_meteo.forecast.models), delete "
            "data/external/_cache/forecast_*, and re-pull. Losing years to NaN "
            "is safe; this is not.\n"
            f"{detail}"
        )
    return report
