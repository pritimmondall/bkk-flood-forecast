"""Loading the feature tables without running out of memory.

The problem this solves
-----------------------
The seven yearly feature tables hold about 25 million rows and 70 columns. Read
naively and concatenated, that is roughly **11.5 GB resident**, and pandas needs
a second copy while concatenating — so peak usage lands near 20 GB. On a laptop
it does not train a model, it kills the kernel.

Three fixes, applied together, bring it under control:

1. **Only read the columns you need.** A classifier for `y_ge15_3h` needs the
   features, that one label, the onset flag and the identifiers. It does not
   need the other eleven labels.

2. **Downcast to float32.** 53 of the 70 columns are stored as doubles. Flood
   depths in centimetres and rainfall in millimetres carry nowhere near 15
   significant digits, so the extra precision is pure waste — and dropping it
   halves the footprint.

3. **Downsample the negatives while loading, not after.** This is the big one.
   At the 15 cm tier roughly 1 row in 3,000 is positive, and training keeps only
   5% of the negatives anyway. Doing that per year *before* concatenating means
   the full frame never exists: 17 million training rows become about 900,000.

Every positive row is always kept. We are short of positives, never of
negatives.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from .config import CFG, PATHS

# Columns that are neither features nor labels but must always survive: without
# them you cannot join a prediction back to a place and a time.
ALWAYS_KEEP = ["station_code", "site_timestamp", "prefix"]


def year_path(year: int, training_dir: Path | None = None) -> Path:
    d = Path(training_dir) if training_dir else PATHS.training
    return d / f"year_{year}.parquet"


def available_years(training_dir: Path | None = None) -> list[int]:
    """Which yearly feature tables have actually been built."""
    d = Path(training_dir) if training_dir else PATHS.training
    years = []
    for path in sorted(d.glob("year_*.parquet")):
        try:
            years.append(int(path.stem.split("_")[1]))
        except (IndexError, ValueError):
            continue
    return years


def unify_categoricals(frames: list[pd.DataFrame],
                       columns: Sequence[str] = ("station_code", "prefix")) -> None:
    """Give every frame the same category list, in place.

    **This is not cosmetic — without it, training fails outright.**

    `build_year` stores `station_code` and `prefix` as categoricals, but BMA
    adds sensors over time, so each yearly file carries a different category
    list (99 stations in 2019, 107 by 2023). When pandas concatenates
    categoricals whose categories disagree, it silently falls back to plain
    object strings — and LightGBM then rejects the frame with "pandas dtypes
    must be int, float or bool". Since `station_code` is a model input, that
    stops training dead.

    Rebuilding over the union of every year's categories keeps the integer
    codes aligned and the dtype intact. `set_categories` only remaps codes, so
    it stays cheap even on millions of rows.
    """
    for column in columns:
        if not all(column in f.columns for f in frames):
            continue
        levels: set = set()
        for f in frames:
            series = f[column]
            levels.update(series.cat.categories
                          if isinstance(series.dtype, pd.CategoricalDtype)
                          else pd.unique(series))
        ordered = sorted(levels)
        for f in frames:
            series = f[column]
            f[column] = (series.cat.set_categories(ordered)
                         if isinstance(series.dtype, pd.CategoricalDtype)
                         else pd.Categorical(series, categories=ordered))


def downcast(df: pd.DataFrame) -> pd.DataFrame:
    """float64 -> float32, and int64 -> the smallest type that fits.

    Halves memory at no meaningful cost. Flood depth in centimetres does not
    need fifteen significant digits, and LightGBM casts to float32 internally
    anyway — so this is removing a conversion, not adding one.
    """
    for column in df.columns:
        kind = df[column].dtype
        if kind == "float64":
            df[column] = df[column].astype("float32")
        elif kind == "int64":
            df[column] = pd.to_numeric(df[column], downcast="integer")
    return df


def _columns_for(path: Path, features: Sequence[str] | None,
                 labels: Sequence[str] | None,
                 extra: Sequence[str] | None) -> list[str] | None:
    """Work out the narrowest column set that satisfies the request."""
    if features is None and labels is None:
        return None                                  # caller wants everything
    present = set(pq.ParquetFile(path).schema.names)
    wanted: list[str] = []
    for group in (ALWAYS_KEEP, features or [], labels or [], extra or []):
        for column in group:
            if column in present and column not in wanted:
                wanted.append(column)
    return wanted


def load_years(years: Iterable[int],
               features: Sequence[str] | None = None,
               labels: Sequence[str] | None = None,
               extra: Sequence[str] | None = None,
               downsample_label: str | None = None,
               negative_frac: float | None = None,
               subsample_frac: float | None = None,
               training_dir: Path | None = None,
               seed: int = 42,
               verbose: bool = False) -> pd.DataFrame:
    """Read the requested years into one frame, as small as it can safely be.

    Parameters
    ----------
    years : which yearly files to read.
    features, labels, extra : restrict the columns. Pass None for everything.
    downsample_label : a binary label column. Every positive row is kept and
        only `negative_frac` of the negatives — applied per year, *before*
        concatenating, so the full frame never has to exist.
    subsample_frac : plain random row sample. For the depth-quantile models,
        where the target is continuous and there are no "negatives" to thin.
    seed : fixed, so a rerun gives the same rows. Reproducibility matters more
        here than variety.

    Notes
    -----
    Never downsample a validation or test split. Thresholds and metrics are only
    meaningful against the true class balance — thinning the negatives would
    inflate precision and quietly invalidate every number downstream.
    """
    if negative_frac is None:
        negative_frac = float(CFG["imbalance"]["negative_downsample_frac"])

    rng_base = np.random.default_rng(seed)
    frames: list[pd.DataFrame] = []
    kept = dropped = 0

    def thin(df: pd.DataFrame) -> pd.DataFrame:
        """Apply whichever sampling the caller asked for."""
        if downsample_label and downsample_label in df.columns:
            positives = df[df[downsample_label] == 1]
            negatives = df[df[downsample_label] != 1]
            if negative_frac < 1.0:
                negatives = negatives.sample(
                    frac=negative_frac,
                    random_state=int(rng_base.integers(0, 2**31 - 1)))
            return pd.concat([positives, negatives])
        if subsample_frac and subsample_frac < 1.0:
            return df.sample(frac=subsample_frac,
                             random_state=int(rng_base.integers(0, 2**31 - 1)))
        return df

    for year in years:
        path = year_path(year, training_dir)
        if not path.exists():
            if verbose:
                print(f"  year_{year}.parquet missing — skipped")
            continue

        columns = _columns_for(path, features, labels, extra)
        handle = pq.ParquetFile(path)
        before = handle.metadata.num_rows

        # Read one row group at a time — roughly a million rows — and thin it
        # immediately. Reading the whole year first would materialise about
        # 850 MB of Arrow plus the same again in pandas during conversion, and
        # the point of thinning is to never pay that.
        pieces = []
        for group in range(handle.metadata.num_row_groups):
            chunk = handle.read_row_group(group, columns=columns).to_pandas()
            chunk = downcast(thin(chunk))
            if len(chunk):
                pieces.append(chunk)
            del chunk

        if not pieces:
            continue
        df = pd.concat(pieces, ignore_index=True) if len(pieces) > 1 else pieces[0]
        del pieces

        # Sequence models and rolling features both depend on chronological
        # order within a station, so restore it after sampling.
        df = df.sort_values(["station_code", "site_timestamp"])

        kept += len(df)
        dropped += before - len(df)
        frames.append(df)

        if verbose:
            note = f" (from {before:,})" if len(df) != before else ""
            print(f"  {year}: {len(df):,} rows{note}")

    if not frames:
        return pd.DataFrame()

    # Must happen before the concat, or the categorical dtype is lost and
    # LightGBM refuses the frame. See `unify_categoricals`.
    unify_categoricals(frames)

    out = pd.concat(frames, ignore_index=True)
    del frames
    if verbose:
        mb = out.memory_usage(deep=True).sum() / 1e6
        print(f"  total: {kept:,} rows, {mb:,.0f} MB in memory"
              + (f" ({dropped:,} negatives dropped)" if dropped else ""))
    return out


def load_fold(fold, features: Sequence[str] | None = None,
              label: str | None = None,
              extra: Sequence[str] | None = None,
              downsample_train: bool = True,
              training_dir: Path | None = None,
              verbose: bool = True) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load one rolling-origin fold as (train, val, test), memory-aware.

    **Training data is downsampled; validation and test are not.** That asymmetry
    is the whole point. Downsampling training data is a speed and stability
    measure with a known correction (calibration). Downsampling evaluation data
    would change the class balance the metrics are computed against, which is not
    a shortcut — it is a wrong answer.
    """
    labels = [label] if label else None
    onset = [c for c in (extra or []) if c.startswith("is_onset")]
    extra = list(extra or [])

    if verbose:
        print(f"  train {fold.train_years} ...")
    train = load_years(fold.train_years, features, labels, extra,
                       downsample_label=label if downsample_train else None,
                       training_dir=training_dir, verbose=verbose)

    if verbose:
        print(f"  val {fold.val_year}, test {fold.test_year} (full, not downsampled) ...")
    val = load_years([fold.val_year], features, labels, extra,
                     training_dir=training_dir, verbose=verbose)
    test = load_years([fold.test_year], features, labels, extra,
                      training_dir=training_dir, verbose=verbose)

    return train, val, test


def feature_list(training_dir: Path | None = None) -> list[str]:
    """The feature names the models were built against, from features.json.

    Read this rather than deriving the list from a DataFrame. It is the contract
    between training and serving, and if the two ever disagree the predictions
    go quietly wrong instead of loudly failing.
    """
    import json
    d = Path(training_dir) if training_dir else PATHS.training
    path = d / "features.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} — run notebooks/03_build_features.ipynb")
    return json.loads(path.read_text())["features"]


def memory_estimate(years: Iterable[int], n_columns: int | None = None,
                    training_dir: Path | None = None) -> dict:
    """How much RAM a naive full load would take. Call this before regretting it."""
    total_rows = 0
    for year in years:
        path = year_path(year, training_dir)
        if path.exists():
            total_rows += pq.ParquetFile(path).metadata.num_rows
    # Measured at roughly 455 bytes/row for the full 70-column table as written,
    # and about 245 after downcasting to float32.
    return {
        "rows": total_rows,
        "gb_naive": round(total_rows * 455 / 1e9, 1),
        "gb_downcast": round(total_rows * 245 / 1e9, 1),
        "gb_downcast_5pct_negatives": round(total_rows * 245 * 0.06 / 1e9, 2),
    }
