"""
Live collectors — one module per source, one registry here.

--------------------------------------------------------------------------
WHAT EACH SOURCE ACTUALLY GIVES US
--------------------------------------------------------------------------
The point of running several APIs is not redundancy. No two of these publish the
same thing; each one fills a different hole, and one of the holes stays open.

| source         | rain            | water level                   | coords   | status      |
|----------------|-----------------|-------------------------------|----------|-------------|
| thaiwater      | none            | canal MSL + flow (11)         | REAL     | COLLECTING  |
| openmeteo      | forecast, 13 km | none                          | grid     | COLLECTING  |
| traffy         | none            | none                          | REAL     | COLLECTING  |
| pumps          | none            | pump station cm, 5-min (~148) | —        | 403, ask BMA|
| pumps_stations | none            | current level + pump status   | **REAL** | 403, ask BMA|
| bma_dds        | YES (131?)      | canal in/out + flow (300?)    | ?        | unreachable |

Only the first three collect today. The other three are written, tested and
waiting on BMA — which is the honest shape of this project: the code is not the
bottleneck, access is.

Read the rain column. Everything obtainable today without asking BMA gives us a
13 km forecast grid and nothing observed. Measured, that combination reaches
**4.9% event POD** against replay's 53% — it catches about one flood in twenty.
Canal level is a multiplier on rain, not a replacement for it.

So this package is worth running for these reasons, none of which is "live
forecasting works now":

1. **It accumulates history that does not otherwise exist.** None of these
   sources publish a downloadable past. Every day the collector does not run is
   real observation at real coordinates gone permanently.
2. **It is the switch.** The day BMA opens the rain gauge feed, one entry in this
   registry takes the same pipeline from ~5% to roughly 45%. Nothing is rebuilt.
3. **It gives us coordinates.** ThaiWater returns genuine positions. Terrain
   currently contributes 0% of model gain solely because every station sits at a
   district centroid.
4. **`pumps` attacks the labels, not the features.** A flood a pump prevented is
   currently labelled "no flood". That is a defect in the ground truth, and no
   model can be trained out of it.

--------------------------------------------------------------------------
USAGE
--------------------------------------------------------------------------
    from bkkflood.collectors import collect_all, coverage_report

    results = collect_all()              # every enabled source, never raises
    print(coverage_report())             # how much history exists yet
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from . import bma_dds, openmeteo, pumps, thaiwater, traffy
from .base import (  # noqa: F401 - re-exported for notebook convenience
    COLLECTOR_VERSION,
    CollectorResult,
    coverage,
    is_due,
    last_poll,
    read_history,
    read_raw,
    reparse_raw,
    run_collector,
    utc_now,
    write_status,
)

__all__ = [
    "CollectorResult", "capability_matrix", "collect_all", "coverage",
    "coverage_report", "is_due", "last_poll", "read_history", "read_raw",
    "reparse_raw", "results_table", "run_collector", "utc_now", "write_status",
    "REGISTRY", "DEFAULT_SOURCES", "history",
    "bma_dds", "openmeteo", "pumps", "thaiwater", "traffy",
]

#: Order matters only for readability of the run log — except that the two
#: sources with no verified endpoint go last, so a slow timeout on them cannot
#: delay the ones that work.
REGISTRY: Dict[str, Dict[str, Any]] = {
    "thaiwater": thaiwater.SPEC,
    "openmeteo": openmeteo.SPEC,
    "traffy": traffy.SPEC,
    "pumps": pumps.SPEC,
    "pumps_stations": pumps.STATIONS_SPEC,
    "bma_dds": bma_dds.SPEC,
}

#: Sources that run on a schedule today.
#:
#: `bma_dds` is deliberately absent. Not out of caution for its own sake — the
#: host is not reachable from any route tried so far, so scheduling it would
#: only write failure rows. When it becomes reachable, the question of whether
#: to poll it is a conversation with BMA, not a config change (project rule 8).
#:
#: `pumps` and `pumps_stations` are NOT scheduled. Their API is fully documented
#: and their parsers are written and tested — but the host sits behind Cloudflare
#: and returns 403 to any HTTP client. See `pumps.py`. Scheduling them would only
#: write a failure row every hour and hammer a government server for nothing.
#: The day BMA grants access, add both names back here; nothing else changes.
#:
#: `collect_all` honours each spec's `cadence_minutes`, so when they do come back
#: one hourly job carries both clocks — the registry walk costs ~148 requests
#: (no bulk endpoint), which is fine daily and rude hourly.
DEFAULT_SOURCES = ("thaiwater", "openmeteo", "traffy")


def collect_all(
    sources: Optional[Iterable[str]] = None,
    dry_run: bool = False,
    write_status_file: bool = True,
    respect_cadence: bool = True,
) -> List[CollectorResult]:
    """Poll every source that is due. One failure never stops the others.

    A dead Open-Meteo must not cost us an hour of ThaiWater — that hour cannot be
    re-fetched later, because ThaiWater has no history endpoint.

    `respect_cadence` also protects against a manual run landing next to a
    scheduled one and doubling the request count on someone else's server.
    """
    names = tuple(sources) if sources else DEFAULT_SOURCES
    out: List[CollectorResult] = []
    for name in names:
        spec = REGISTRY.get(name)
        if spec is None:
            continue

        cadence = spec.get("cadence_minutes") or 0
        if respect_cadence and not dry_run and not is_due(spec["name"], cadence):
            res = CollectorResult(spec["name"], utc_now(), ok=True, skipped=True)
            res.notes.append(f"not due — cadence {cadence} min")
            out.append(res)
            continue

        out.append(
            run_collector(
                source=spec["name"],
                fetch=spec["fetch"],
                time_col=spec.get("time_col"),
                dry_run=dry_run,
            )
        )
    if write_status_file and not dry_run:
        write_status(out)
    return out


def results_table(results: List[CollectorResult]) -> pd.DataFrame:
    return pd.DataFrame([r.as_row() for r in results])


def coverage_report(sources: Optional[Iterable[str]] = None) -> pd.DataFrame:
    """History accumulated per source, and whether we are still in cold start.

    `fl_max_24h` and `rain_rf24hr_mean` look back 24 hours. Until every source
    reports `cold_start = False`, live mode must refuse to emit alerts.
    """
    names = tuple(sources) if sources else DEFAULT_SOURCES
    return pd.DataFrame([coverage(n) for n in names])


def capability_matrix() -> pd.DataFrame:
    """What each source provides — the table at the top of this docstring, live."""
    return pd.DataFrame(
        [
            {
                "source": s["name"],
                "provides": "; ".join(s["provides"]),
                "cadence_min": s["cadence_minutes"],
                "needs_permission": s["needs_permission"],
                "scheduled": s["name"] in DEFAULT_SOURCES,
                "verified": s["verified"],
            }
            for s in REGISTRY.values()
        ]
    )


#: Sources whose `parse()` accepts a `now=` argument, so a reparse can
#: reconstruct time-relative columns (`age_minutes`) as they were at fetch time
#: rather than as they would be now.
_PARSE_TAKES_NOW = {"thaiwater"}


def history(source: str, repair: bool = True) -> pd.DataFrame:
    """A source's history, rebuilt from raw payloads when the parser has moved on.

    Prefer this over `read_history` in notebooks and anywhere the values matter.

    Two things can make the stored parquet untrustworthy, and only one of them is
    obvious:

    1. **A missing column.** Easy to spot — compare the column sets.
    2. **A column whose MEANING changed.** Much worse. When `thaiwater.ts` went
       from Asia/Bangkok to UTC, rows written by the old parser kept the same
       column name holding local time. Concatenating them with new rows produces
       a frame with every expected column and two different timezones inside one
       of them. No column check can see that, and the first version of this
       function returned it happily — the notebook's own "no readings from the
       future" assertion is what caught it.

    So the version stamp on every row is the real signal: any row not written by
    the current `COLLECTOR_VERSION` means reparse. Columns are a secondary
    trigger for the case where a parser gained a field without a version bump.

    Nothing on disk is rewritten. Conforming old data to today's parser would
    destroy the evidence of what the API actually sent.
    """
    stored = read_history(source)
    if not repair or stored.empty:
        return stored

    module = {"thaiwater": thaiwater, "traffy": traffy, "openmeteo": openmeteo,
              "pumps": pumps}.get(source)
    parse_fn = (getattr(module, "parse", None)
                or getattr(module, "parse_levels", None)) if module else None
    if parse_fn is None:
        return stored

    stale_version = (
        "_collector_version" not in stored.columns
        or (stored["_collector_version"].astype(str) != COLLECTOR_VERSION).any()
    )
    rebuilt = reparse_raw(source, parse_fn, pass_now=source in _PARSE_TAKES_NOW)
    if rebuilt.empty:
        return stored

    missing_columns = bool(set(rebuilt.columns) - set(stored.columns))
    if stale_version or missing_columns:
        return rebuilt
    return stored
