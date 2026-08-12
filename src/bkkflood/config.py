"""
Loading the one config file.

Why this exists: every threshold, year, path and exclusion in the project lives
in config/config.yaml. This module finds that file no matter which directory
you started Jupyter from, and hands it back as a plain dictionary.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml

_MARKER = "config/config.yaml"


@lru_cache(maxsize=1)
def project_root() -> Path:
    """Find the repository root.

    Walks up from this file (and from the current working directory, which
    matters when the package is installed rather than imported from source)
    until it finds config/config.yaml.
    """
    candidates = [Path(__file__).resolve(), Path.cwd().resolve()]
    for start in candidates:
        for parent in [start, *start.parents]:
            if (parent / _MARKER).is_file():
                return parent
    env = os.environ.get("BKKFLOOD_ROOT")
    if env and (Path(env) / _MARKER).is_file():
        return Path(env)
    raise FileNotFoundError(
        "Could not locate config/config.yaml. Run from inside the repository, "
        "or set the BKKFLOOD_ROOT environment variable to the repo root."
    )


@lru_cache(maxsize=1)
def load_config() -> Dict[str, Any]:
    """Read config/config.yaml into a dictionary."""
    with open(project_root() / _MARKER, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def resolve(*parts: str) -> Path:
    """Turn a repo-relative path into an absolute one.

    >>> resolve("data", "interim")
    PosixPath('/.../bkk-flood-forecast/data/interim')
    """
    return project_root().joinpath(*parts)


def config_path(key: str) -> Path:
    """Resolve one of the entries under `paths:` in the config.

    >>> config_path("interim")
    PosixPath('/.../data/interim')
    """
    cfg = load_config()
    value = cfg["paths"][key]
    if not isinstance(value, str):
        raise TypeError(f"paths.{key} is not a single path (got {type(value)})")
    return resolve(value)
