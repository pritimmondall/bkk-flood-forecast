"""
bkkflood — shared code for the Bangkok Flood Forecast project.

This library is deliberately thin. All *work* happens in the notebooks; this
package only holds the functions that more than one notebook needs, so that
there is exactly one definition of "how we read a raw CSV", "what counts as a
flood event", and so on.

If you find yourself copying a function out of here into a notebook, stop —
that is how training and serving quietly drift apart.

Everything reads its constants from config/config.yaml. Nothing here hard-codes
a threshold, a year, or a station exclusion.

--------------------------------------------------------------------------
WHY THE IMPORTS ARE LAZY
--------------------------------------------------------------------------
This file used to import every submodule eagerly. That meant `import bkkflood`
pulled in duckdb, LightGBM, rasterio and geopandas — the entire modelling stack —
no matter what you actually wanted.

Two things broke because of it:

1. Running the tests under a Python that is not the project venv failed at
   collection with `No module named 'duckdb'`, before a single test ran, even for
   tests that touch nothing heavier than pandas.
2. More importantly for where this is going: `scripts/run_live_collect.sh` is
   meant to run hourly on a small always-on box — a Raspberry Pi or a cheap VPS.
   Eager imports would have meant installing LightGBM and rasterio on that box
   just to poll four public APIs.

So names now resolve on first use (PEP 562). `import bkkflood.collectors` needs
`requests`, `pandas` and `pyarrow`, and nothing else. `bkkflood.train_classifier`
still imports LightGBM — but only when you reach for it, and the ImportError you
get then names the thing you actually asked for.
"""

from __future__ import annotations

import importlib
from typing import Any

__version__ = "3.0.0"

#: name -> submodule it lives in. This is the whole public surface; adding a
#: function to a submodule does not publish it here until it is listed.
_LAZY: dict[str, str] = {}


def _register(module: str, *names: str) -> None:
    for n in names:
        _LAZY[n] = module


_register("config", "load_config", "project_root", "resolve")
_register(
    "rawio",
    "DATASETS", "connect", "raw_file", "raw_files", "read_raw_sql",
    "ingest_year_to_parquet", "interim_path", "manifest_path", "interim_sql",
    "verify_ordering",
)
_register("quality", "station_year_profile", "quality_scorecard")
_register(
    "events",
    "detect_excursions", "assemble_events", "detect_events",
    "detect_events_all_tiers", "class_balance",
)
_register(
    "labels",
    "build_labels", "labels_sql", "label_summary", "check_labels_against_raw",
)
_register(
    "features",
    "flood_features", "rain_features", "water_flow_features",
    "write_feature_table", "load_features", "feature_columns",
)
_register(
    "evaluate",
    "average_precision", "binary_metrics", "pr_auc", "pr_curve", "brier",
    "best_threshold", "by_onset", "event_pod", "folds", "embargo_mask",
    "scorable",
)
_register(
    "baselines",
    "persistence", "climatology", "apply_climatology", "rain_rule",
    "run_baselines",
)
_register(
    "models",
    "feature_set", "build_matrix", "correct_for_downsampling",
    "train_classifier", "train_quantile", "score_year", "gain_importance",
    "save_model", "run_fold",
)
_register(
    "calibration",
    "reliability_curve", "expected_calibration_error", "isotonic_fit",
    "apply_isotonic", "quantile_coverage", "coverage_verdict",
    "lead_time_distribution",
)
_register("stations", "district_prefix", "load_registry", "prefix_coverage")
_register(
    "external",
    "district_points", "fetch_forecast_rain", "fetch_era5_rain",
    "coverage_report", "fetch_traffy", "is_flood_report",
    "assert_forecast_is_not_reanalysis",
)
_register("terrain", "ground_mask", "road_mask")

#: Submodules reachable as `bkkflood.<name>` without importing them up front.
_SUBMODULES = (
    "baselines", "calibration", "collectors", "config", "evaluate", "events",
    "external", "features", "labels", "models", "quality", "rawio", "serving",
    "stations", "terrain",
)

__all__ = sorted(set(_LAZY) | set(_SUBMODULES) | {"__version__"})


def __getattr__(name: str) -> Any:
    """Resolve a public name on first use (PEP 562)."""
    if name in _SUBMODULES:
        mod = importlib.import_module(f".{name}", __name__)
        globals()[name] = mod
        return mod

    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    obj = getattr(importlib.import_module(f".{module}", __name__), name)
    globals()[name] = obj  # cache, so the lookup happens once
    return obj


def __dir__() -> list[str]:
    return __all__
