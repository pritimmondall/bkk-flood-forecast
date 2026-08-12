"""
Shared machinery for every live collector.

--------------------------------------------------------------------------
WHY THIS IS APPEND-ONLY, AND WHY IT LOOKS OVER-ENGINEERED
--------------------------------------------------------------------------
None of the sources we poll publish a downloadable past. ThaiWater and
`weather.bangkok.go.th` return *current values only*. That means this directory
is not a cache of something we could re-download — it IS the historical record,
and it exists only because the collector ran. A bug that overwrites a day is not
an inconvenience; it is data that no longer exists anywhere.

So: every fetch writes its own new file and nothing is ever read-modify-written.

    data/live/<source>/dt=<YYYY-MM-DD>/part-<YYYYMMDDTHHMMSSZ>.parquet
    data/live/_raw/<source>/dt=<YYYY-MM-DD>/<YYYYMMDDTHHMMSSZ>.json.gz

The raw JSON is kept as well, gzipped. It costs almost nothing and it means a
parser bug discovered in three months is recoverable — we re-parse rather than
lose a season. Parsers are guesses about someone else's undocumented API; assume
at least one of them is wrong.

The partition layout is DuckDB-native, so the rest of the project reads it with
the same `read_parquet` it already uses:

    SELECT * FROM read_parquet('data/live/thaiwater/**/*.parquet')

--------------------------------------------------------------------------
PROVENANCE
--------------------------------------------------------------------------
Every row carries `_source`, `_fetched_at_utc` and `_collector_version`. When two
sources disagree about a canal, the answer to "which one said this, and when did
we ask" must be in the data, not in someone's memory.
"""

from __future__ import annotations

import gzip
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

log = logging.getLogger(__name__)

#: Bump this whenever a parser changes what a VALUE means, not just when a
#: column is added. `history()` uses it to decide whether the stored parquet can
#: be trusted, and a version that lags reality is worse than no version at all.
#:
#: 1.1.0 — thaiwater `ts` converted from Asia/Bangkok to UTC. Rows written by
#:         1.0.0 hold local time in the same column, so a mixed history silently
#:         mixes two timezones. Columns alone cannot detect that.
COLLECTOR_VERSION = "1.1.0"

#: Never hammer a government API. These are polite defaults, not tuning knobs.
DEFAULT_TIMEOUT = 30
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 2.0


# ---------------------------------------------------------------------------
# Where things land
# ---------------------------------------------------------------------------
def _repo_root() -> Path:
    """Where `data/live/` lives.

    `BKKFLOOD_REPO` wins if set. It exists because the scheduler (launchd) runs
    with a working directory nobody controls, and a collector that silently
    writes its history into the wrong tree is indistinguishable from one that is
    working — until the day you look for six months of data and it is not there.
    """
    import os

    env = os.environ.get("BKKFLOOD_REPO")
    if env:
        p = Path(env).expanduser().resolve()
        if p.exists():
            return p

    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config" / "config.yaml").exists():
            return parent
    # Fall back to three levels up: src/bkkflood/collectors -> repo
    return here.parents[3]


def live_dir(source: str, when: datetime, raw: bool = False) -> Path:
    root = _repo_root()
    day = when.strftime("%Y-%m-%d")
    base = root / "data" / "live"
    return (base / "_raw" / source / f"dt={day}") if raw else (base / source / f"dt={day}")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(when: datetime) -> str:
    return when.strftime("%Y%m%dT%H%M%SZ")


# ---------------------------------------------------------------------------
# The result of one poll
# ---------------------------------------------------------------------------
@dataclass
class CollectorResult:
    """What one `fetch()` produced. Never raises past the runner."""

    source: str
    fetched_at: datetime
    ok: bool
    n_rows: int = 0
    path: Optional[Path] = None
    raw_path: Optional[Path] = None
    error: Optional[str] = None
    latest_reading: Optional[str] = None
    notes: List[str] = field(default_factory=list)
    skipped: bool = False

    def as_row(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "ok": self.ok,
            "skipped": self.skipped,
            "rows": self.n_rows,
            "latest_reading": self.latest_reading,
            "fetched_at_utc": self.fetched_at.strftime("%Y-%m-%d %H:%M:%S"),
            "error": (self.error or "")[:120],
            "file": self.path.name if self.path else None,
        }


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def http_get_json(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    backoff: float = DEFAULT_BACKOFF,
    headers: Optional[Dict[str, str]] = None,
) -> Any:
    """GET and parse JSON, with a polite exponential backoff.

    Raises on final failure. Callers wrap in `run_collector`, which turns the
    exception into a failed `CollectorResult` — one dead source must never stop
    the others from collecting. A missing hour of ThaiWater because Open-Meteo
    was down would be an unforced error.
    """
    import time

    import requests

    hdrs = {"User-Agent": "bkk-flood-forecast/1.0 (research collector)"}
    hdrs.update(headers or {})

    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=timeout, headers=hdrs)
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
            last = exc
            if attempt < retries - 1:
                time.sleep(backoff ** attempt)
    raise RuntimeError(f"GET {url} failed after {retries} attempts: {last}")


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------
def _unique_path(d: Path, prefix: str, suffix: str, when: datetime) -> Path:
    """A path that does not already exist.

    Two polls inside the same second are unlikely on an hourly schedule but not
    impossible — a manual run next to a scheduled one, a retry, a backfill loop.
    Silently clobbering a file in an append-only store is exactly the bug this
    module exists to prevent, so the check is unconditional rather than a comment
    about how it cannot happen.
    """
    p = d / f"{prefix}{_stamp(when)}{suffix}"
    if not p.exists():
        return p
    p = d / f"{prefix}{_stamp(when)}-{int(when.microsecond):06d}{suffix}"
    n = 0
    while p.exists():
        n += 1
        p = d / f"{prefix}{_stamp(when)}-{int(when.microsecond):06d}-{n}{suffix}"
    return p


def write_raw(source: str, payload: Any, when: datetime) -> Path:
    """Persist the untouched response before we try to understand it."""
    d = live_dir(source, when, raw=True)
    d.mkdir(parents=True, exist_ok=True)
    p = _unique_path(d, "", ".json.gz", when)
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    return p


def write_parquet(df: pd.DataFrame, source: str, when: datetime) -> Path:
    """One fetch, one new file. Nothing is ever overwritten."""
    d = live_dir(source, when)
    d.mkdir(parents=True, exist_ok=True)
    p = _unique_path(d, "part-", ".parquet", when)
    df.to_parquet(p, index=False)
    return p


def stamp_provenance(df: pd.DataFrame, source: str, when: datetime) -> pd.DataFrame:
    df = df.copy()
    df["_source"] = source
    df["_fetched_at_utc"] = pd.Timestamp(when).tz_localize(None)
    df["_collector_version"] = COLLECTOR_VERSION
    return df


# ---------------------------------------------------------------------------
# The runner
# ---------------------------------------------------------------------------
def run_collector(
    source: str,
    fetch: Callable[[], "tuple[pd.DataFrame, Any]"],
    time_col: Optional[str] = None,
    dry_run: bool = False,
) -> CollectorResult:
    """Call one collector's `fetch()`, persist what it returned, never raise.

    `fetch` returns `(dataframe, raw_payload)`. The raw payload is written first,
    so that even a parser that crashes leaves the observation on disk.
    """
    when = utc_now()
    try:
        df, raw = fetch()
    except Exception as exc:  # noqa: BLE001
        log.warning("%s failed: %s", source, exc)
        return CollectorResult(source, when, ok=False, error=str(exc))

    res = CollectorResult(source, when, ok=True, n_rows=len(df))

    if time_col and time_col in df.columns and len(df):
        try:
            res.latest_reading = str(pd.to_datetime(df[time_col], errors="coerce").max())
        except Exception:  # noqa: BLE001
            pass

    if df.empty:
        res.notes.append("returned zero rows — endpoint reachable but empty")

    if dry_run:
        res.notes.append("dry run — nothing written")
        return res

    try:
        res.raw_path = write_raw(source, raw, when)
    except Exception as exc:  # noqa: BLE001
        res.notes.append(f"raw write failed: {exc}")

    if not df.empty:
        res.path = write_parquet(stamp_provenance(df, source, when), source, when)
    return res


# ---------------------------------------------------------------------------
# Reading it back
# ---------------------------------------------------------------------------
def read_history(source: str) -> pd.DataFrame:
    """Everything collected so far for one source."""
    root = _repo_root() / "data" / "live" / source
    files = sorted(root.glob("dt=*/part-*.parquet"))
    if not files:
        return pd.DataFrame()
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def last_poll(source: str) -> Optional[datetime]:
    """When this source was last collected, from the filenames alone.

    Reads the directory listing rather than the parquet contents — this runs
    before every poll, and opening a season of files to answer "have we been
    here recently" would make the cheap check the expensive one.
    """
    root = _repo_root() / "data" / "live" / source
    stamps: List[datetime] = []
    for p in root.glob("dt=*/part-*.parquet"):
        token = p.stem.replace("part-", "").split("-")[0]
        try:
            stamps.append(datetime.strptime(token, "%Y%m%dT%H%M%SZ")
                          .replace(tzinfo=timezone.utc))
        except ValueError:
            continue
    return max(stamps) if stamps else None


def is_due(source: str, cadence_minutes: float, tolerance: float = 0.8) -> bool:
    """Has enough time passed to poll this source again?

    The tolerance exists because launchd's hourly timer drifts by seconds to
    minutes. A strict `>= 60 min` test against an hourly job would skip roughly
    every other run, which is a data-loss bug disguised as politeness.

    The real work this does is letting one hourly job carry sources on different
    clocks: `pumps_stations` costs ~148 requests because there is no bulk
    endpoint, so it runs daily while everything else runs hourly.
    """
    if not cadence_minutes:
        return True
    last = last_poll(source)
    if last is None:
        return True
    elapsed_min = (utc_now() - last).total_seconds() / 60.0
    return elapsed_min >= cadence_minutes * tolerance


def write_status(results: List["CollectorResult"]) -> Path:
    """One small JSON with the outcome of the most recent run.

    This is what a dashboard or a morning check reads instead of tailing a log.
    It is overwritten every run — deliberately, and it is the only file in this
    package that is: it describes *now*, it is not a record of anything, and it
    can be rebuilt from the parquet at any time.
    """
    root = _repo_root() / "data" / "live"
    root.mkdir(parents=True, exist_ok=True)
    p = root / "_status.json"
    payload = {
        "written_at_utc": utc_now().isoformat(),
        "collector_version": COLLECTOR_VERSION,
        "sources": [r.as_row() | {"notes": r.notes} for r in results],
        "n_ok": sum(1 for r in results if r.ok and not r.skipped),
        "n_failed": sum(1 for r in results if not r.ok),
        "n_skipped": sum(1 for r in results if r.skipped),
    }
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def read_raw(source: str) -> List["tuple[datetime, Any]"]:
    """Every stored raw payload for a source, with the time it was fetched."""
    root = _repo_root() / "data" / "live" / "_raw" / source
    out: List["tuple[datetime, Any]"] = []
    for p in sorted(root.glob("dt=*/*.json.gz")):
        token = p.name.split(".")[0].split("-")[0]
        try:
            when = datetime.strptime(token, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            out.append((when, json.load(fh)))
    return out


def reparse_raw(source: str, parse_fn: Callable[..., pd.DataFrame],
                pass_now: bool = False) -> pd.DataFrame:
    """Rebuild a source's entire history from the stored raw payloads.

    This is the promise the raw files were kept for, and it is not hypothetical:
    the ThaiWater parser gained a timezone conversion, a station label and a
    bank-reference flag *after* the first collection had already been written.
    Without the raw payloads that first hour would have been permanently
    second-class — present, but missing columns everything downstream expects.

    Nothing is written. The append-only store stays exactly as it was; this
    returns the corrected frame and lets the caller decide what to do with it.
    That matters: silently rewriting history to match today's parser would
    destroy the evidence of what the API actually sent.
    """
    frames: List[pd.DataFrame] = []
    for when, payload in read_raw(source):
        df = parse_fn(payload, now=when) if pass_now else parse_fn(payload)
        if df is None or df.empty:
            continue
        frames.append(stamp_provenance(df, source, when))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def coverage(source: str) -> Dict[str, Any]:
    """How much history exists — the input to the cold-start decision.

    `fl_max_24h` and `rain_rf24hr_mean` look back 24 hours. Until this reports
    at least 24 hours of continuous collection, live mode must refuse to emit
    alerts. A confident zero from a system with no history is the worst possible
    output, and it is the failure mode most likely to be mistaken for success.
    """
    df = read_history(source)
    if df.empty:
        return {"source": source, "polls": 0, "rows": 0, "first": None,
                "last": None, "hours": 0.0, "cold_start": True}
    t = pd.to_datetime(df["_fetched_at_utc"])
    hours = (t.max() - t.min()).total_seconds() / 3600.0
    return {
        "source": source,
        "polls": int(t.nunique()),
        "rows": int(len(df)),
        "first": str(t.min()),
        "last": str(t.max()),
        "hours": round(hours, 2),
        "cold_start": hours < 24,
    }
