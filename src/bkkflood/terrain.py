"""
Terrain features from the 1 metre DTM.

--------------------------------------------------------------------------
WHY THIS MODULE EXISTS
--------------------------------------------------------------------------
Every earlier version of this project tested terrain using a 31 m SRTM model,
found every correlation below 0.08, and concluded that terrain does not predict
flooding in Bangkok.

That test could not have succeeded. Urban water collects in dips 20-50 cm deep
and a few metres across. A 31 m pixel averages a whole city block into one
number, so the dip is gone before the model ever sees it. The conclusion was
about the resolution, not about the terrain.

`data/DTM_1M/DTM_1M.tif` is a 13.9 GB, 1 metre model covering the entire city.
It has been sitting in `data/` unused, and earlier documents listed
high-resolution elevation as *missing data to request from BMA*. It is not
missing. This module is the retest.

--------------------------------------------------------------------------
THE ONE NUMBER THAT SHAPES EVERYTHING HERE
--------------------------------------------------------------------------
Bangkok has roughly four metres of relief across the entire city, and a median
ground level near 1 m. In terrain that flat:

  * slope is almost meaningless - it is nearly zero everywhere, and what little
    signal exists is dominated by the noise floor of the survey;
  * "uphill vs downhill" barely applies;
  * **depression depth is the whole story**. "How much of a dip is this, and how
    deep does water have to get before it spills out" is the physically real
    question, and it is answerable at 1 m.

So `depression_depth_m` is the headline feature. Slope and TWI are computed
because the spec asks for them, and are reported with their limitations
attached rather than presented as equals.

--------------------------------------------------------------------------
TWO RESOLUTIONS, ON PURPOSE
--------------------------------------------------------------------------
  local    elevation, slope, depression depth. Computed at the full 1 m, one
           district at a time, in tiles. These are local properties, so tiling
           with an overlap is exact for anything smaller than the overlap.

  routing  flow accumulation and TWI. These are NOT local - a cell's upslope
           area depends on the whole catchment above it, which crosses district
           boundaries. Computed over the entire city in a single pass at a
           coarser resolution so it fits in memory.

Mixing those up gives you either a correct answer you cannot afford or a cheap
answer that is wrong.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from .config import load_config, resolve

# Heavy geo dependencies are imported lazily so that `import bkkflood` still
# works on a machine that only needs the Phase 0 tools.
try:  # pragma: no cover
    import rasterio
    from rasterio.windows import Window, from_bounds
    from rasterio.transform import Affine
    _HAS_RASTERIO = True
except ImportError:  # pragma: no cover
    _HAS_RASTERIO = False


# ---------------------------------------------------------------------------
# Loading the boundaries and the raster
# ---------------------------------------------------------------------------
def districts(to_crs: Optional[str] = None):
    """Bangkok's 50 districts, reprojected to the DTM's CRS by default.

    The GeoJSON is in WGS84 (degrees) and the DTM is in UTM zone 47N (metres).
    Everything in this module works in metres, because "500 m of buffer" is a
    sentence you can reason about and "0.0045 degrees" is not.
    """
    import geopandas as gpd

    cfg = load_config()
    gdf = gpd.read_file(resolve(cfg["paths"]["districts"]))
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    return gdf.to_crs(to_crs or cfg["terrain"]["working_crs"])


def dtm_path():
    cfg = load_config()
    return resolve(cfg["paths"][cfg["terrain"]["source"]])


def dtm_profile() -> Dict:
    """Metadata for the DTM, without reading any pixels."""
    _require_rasterio()
    with rasterio.open(dtm_path()) as src:
        return {
            "path": str(dtm_path()),
            "crs": str(src.crs),
            "width": src.width,
            "height": src.height,
            "resolution_m": float(src.res[0]),
            "dtype": src.dtypes[0],
            "nodata": src.nodata,
            "overviews": src.overviews(1),
            "bounds": tuple(src.bounds),
            "gigapixels": round(src.width * src.height / 1e9, 2),
        }


def _require_rasterio():
    if not _HAS_RASTERIO:
        raise ImportError(
            "rasterio is required for terrain work. "
            "pip install rasterio geopandas scikit-image scipy"
        )


# ---------------------------------------------------------------------------
# Reading a piece of the raster
# ---------------------------------------------------------------------------
@dataclass
class Patch:
    """A rectangle of terrain, plus everything needed to put it back on a map."""
    dem: np.ndarray            # float32, NaN where there is no data
    valid: np.ndarray          # bool, True where the DEM has a real value
    transform: "Affine"
    cellsize_m: float
    bounds: Tuple[float, float, float, float]

    @property
    def valid_share(self) -> float:
        return float(self.valid.mean()) if self.valid.size else 0.0


def read_patch(bounds, resolution_m: float = 1.0, src=None) -> Patch:
    """Read one rectangle of the DTM at a chosen resolution.

    `bounds` is (minx, miny, maxx, maxy) in the raster's CRS (metres).

    Coarsening is done by rasterio's decimated read, which uses the overview
    pyramid already built into the file — so asking for 10 m costs a hundredth
    of what asking for 1 m costs, rather than reading everything and throwing
    99% of it away.

    Nodata becomes NaN. That matters: this DTM is a rectangle containing a
    city-shaped hole of real data, and treating the 53% of nodata as "elevation
    zero" would invent a cliff around the entire boundary of Bangkok.
    """
    _require_rasterio()
    close_after = src is None
    src = src or rasterio.open(dtm_path())
    try:
        win = from_bounds(*bounds, transform=src.transform)
        win = win.round_offsets().round_lengths()
        # Clip to the raster so a buffer hanging off the edge does not fail.
        win = win.intersection(Window(0, 0, src.width, src.height))

        native = float(src.res[0])
        factor = max(1, int(round(resolution_m / native)))
        out_h = max(1, int(win.height) // factor)
        out_w = max(1, int(win.width) // factor)

        dem = src.read(1, window=win, out_shape=(out_h, out_w)).astype("float32")
        transform = src.window_transform(win) * Affine.scale(factor, factor)

        nodata = src.nodata
        valid = np.isfinite(dem)
        if nodata is not None:
            valid &= dem != nodata
        # LiDAR nodata sentinels are enormous negative floats; a sanity band
        # catches any that slipped through a resampling average.
        valid &= (dem > -100) & (dem < 500)
        dem = np.where(valid, dem, np.nan)

        return Patch(dem=dem, valid=valid, transform=transform,
                     cellsize_m=native * factor,
                     bounds=tuple(rasterio.windows.bounds(win, src.transform)))
    finally:
        if close_after:
            src.close()


def iter_tiles(height: int, width: int, tile_px: int, overlap_px: int):
    """Yield (row_slice, col_slice, core_slice) covering an array in tiles.

    The tile is read with an overlap so that neighbourhood operations near the
    edge are computed with real neighbours; the `core` slice is the part that
    gets kept, so tiles do not double-count.
    """
    step = tile_px - 2 * overlap_px
    if step <= 0:
        raise ValueError("tile_px must be more than twice tile_overlap_px")
    for r0 in range(0, height, step):
        for c0 in range(0, width, step):
            r1 = min(r0 + tile_px, height)
            c1 = min(c0 + tile_px, width)
            core_r0 = overlap_px if r0 > 0 else 0
            core_c0 = overlap_px if c0 > 0 else 0
            core_r1 = (r1 - r0) - (overlap_px if r1 < height else 0)
            core_c1 = (c1 - c0) - (overlap_px if c1 < width else 0)
            yield (slice(r0, r1), slice(c0, c1),
                   (slice(core_r0, core_r1), slice(core_c0, core_c1)))


# ---------------------------------------------------------------------------
# The local features
# ---------------------------------------------------------------------------
def ground_mask(dem: np.ndarray, cellsize_m: float = 1.0,
                window_m: Optional[float] = None,
                tolerance_m: Optional[float] = None) -> np.ndarray:
    """Select the cells that are actually ground: streets, canals, open land.

    WHY THIS IS NEEDED. `DTM_1M` is not bare earth in dense districts. Buildings
    were stripped from a surface model and the holes interpolated, so over a
    large footprint the fill drifts up toward roof height. Measured: median
    "ground" in Pathum Wan is 4.57 m and Bang Rak 4.55 m, against 0.63 m in open
    Lat Krabang. Bangkok's inner districts are not four metres higher than its
    outskirts.

    HOW THIS RECOVERS IT. The contamination is one-sided: interpolated buildings
    sit *above* the real surface, never below. Streets, canals and open land form
    the low surface, and they form a connected network through every district.
    So take a rolling minimum over a window wider than a city block, and keep the
    cells within a tolerance of it. What survives is the surface water runs on.

    Measured effect at the defaults (100 m window, 1.0 m tolerance), median
    elevation of a 1.5 km window at each district centre:

        Bang Rak      4.65 m  ->  1.72 m
        Pathum Wan    4.54 m  ->  2.69 m
        Lat Krabang   0.56 m  ->  0.32 m   (open ground: barely moves, as it should)

    The control matters as much as the treatment. A mask that also dragged Lat
    Krabang down would be selecting canal beds, not streets — which is exactly
    what happens past about a 150 m window, where open districts go negative.

    WHAT THIS IS NOT. It is an estimate of the low surface, not a true bare-earth
    model, and it cannot distinguish a street from a canal or a car park. It is a
    workaround for a raster that is not what its filename says. The better
    answers, in order: ask BMA what `DTM_1M` actually is, and mask to real road
    centrelines (`road_mask()`), which is what the supervisor's
    `Flood Depth = Water Level - Road Elevation` formula actually needs.
    """
    from scipy.ndimage import minimum_filter

    cfg = load_config()["terrain"]["ground_mask"]
    win = window_m if window_m is not None else cfg["window_m"]
    tol = tolerance_m if tolerance_m is not None else cfg["tolerance_m"]

    valid = np.isfinite(dem)
    if not valid.any():
        return valid

    # inf outside the data so nodata never wins the minimum
    z = np.where(valid, dem, np.inf)
    px = max(3, int(round(win / cellsize_m)))
    local_low = minimum_filter(z, size=px, mode="nearest")
    return valid & (dem <= local_low + tol)


def road_mask(geometry, shape, transform, roads=None, buffer_m: float = 8.0):
    """Rasterise OSM road centrelines into a boolean mask. The better method.

    `ground_mask()` above infers the low surface from the raster. This uses actual
    road geometry, which is more principled for two reasons: it cannot mistake a
    canal or a car park for a street, and it produces the *road* elevation the
    supervisor's `Flood Depth = Water Level - Road Elevation` formula asks for.

    It needs OSM data, which has to be fetched separately (see
    `scripts/fetch_osm_roads.py` — Overpass is not reachable from every network).
    Where roads are unavailable, `ground_mask()` is the fallback and the notebook
    reports which was used per district.
    """
    _require_rasterio()
    from rasterio.features import rasterize

    if roads is None or len(roads) == 0:
        return np.zeros(shape, dtype=bool)
    buffered = [g.buffer(buffer_m) for g in roads.geometry if g is not None]
    if not buffered:
        return np.zeros(shape, dtype=bool)
    return rasterize(((g, 1) for g in buffered), out_shape=shape,
                     transform=transform, fill=0, dtype="uint8").astype(bool)


def fill_depressions(dem: np.ndarray) -> np.ndarray:
    """Return the surface you would get if every hollow were filled to its brim.

    This is morphological reconstruction by erosion — the standard sink-filling
    algorithm. Picture pouring water over the terrain until nothing can drain
    any further: the result is the original surface everywhere except inside
    hollows, where it is flat at the level of the lowest point on the rim.

    NaN (outside the city) is treated as an open edge, so a depression touching
    the boundary drains out rather than filling to the height of the whole city.
    """
    from skimage.morphology import reconstruction

    work = dem.copy()
    missing = ~np.isfinite(work)
    if missing.all():
        return work

    # Seed: high everywhere except the borders and the edges of the nodata
    # region, which are held at the original elevation so water can escape.
    seed = np.full(work.shape, np.nanmax(work), dtype="float64")
    filled_dem = np.where(missing, np.nanmax(work), work).astype("float64")

    border = np.zeros(work.shape, dtype=bool)
    border[0, :] = border[-1, :] = True
    border[:, 0] = border[:, -1] = True
    # Any valid cell adjacent to nodata is also an outlet.
    if missing.any():
        from scipy.ndimage import binary_dilation
        border |= binary_dilation(missing) & ~missing
    seed[border] = filled_dem[border]

    filled = reconstruction(seed, filled_dem, method="erosion")
    filled = np.where(missing, np.nan, filled)
    return filled.astype("float32")


def depression_depth(dem: np.ndarray, filled: Optional[np.ndarray] = None,
                     min_depth_m: Optional[float] = None) -> np.ndarray:
    """How far below its surroundings each point sits, in metres.

    Zero on a slope or a flat. Positive inside a hollow, and the value is
    literally "how deep the water would be here if this dip filled to the brim".

    That is the single most physically meaningful terrain number for this
    project: it is measured in the same units, on the same scale, as the thing
    we are predicting.
    """
    cfg = load_config()["terrain"]
    if filled is None:
        filled = fill_depressions(dem)
    depth = filled - dem
    floor = cfg["min_depression_depth_m"] if min_depth_m is None else min_depth_m
    depth = np.where(np.isfinite(depth) & (depth >= floor), depth, 0.0)
    return np.where(np.isfinite(dem), depth, np.nan).astype("float32")


def slope_degrees(dem: np.ndarray, cellsize_m: float) -> np.ndarray:
    """Steepest slope at each cell, in degrees (Horn's method).

    Expect very small numbers. Bangkok's whole relief is about four metres, so
    a "steep" slope here is a kerb. Reported because the spec asks for it, and
    because near-zero slope with a deep depression is a genuinely informative
    combination: it means water that arrives has nowhere to go.
    """
    z = np.where(np.isfinite(dem), dem, np.nan)
    dzdx = np.gradient(z, cellsize_m, axis=1)
    dzdy = np.gradient(z, cellsize_m, axis=0)
    return np.degrees(np.arctan(np.hypot(dzdx, dzdy))).astype("float32")


# ---------------------------------------------------------------------------
# The routing features (non-local)
# ---------------------------------------------------------------------------
_D8_OFFSETS = [(-1, -1), (-1, 0), (-1, 1),
               (0, -1),           (0, 1),
               (1, -1),  (1, 0),  (1, 1)]


def routing_surface(dem: np.ndarray, filled: Optional[np.ndarray] = None,
                    epsilon: float = 1e-3) -> np.ndarray:
    """The surface to route water over. Do not skip this step.

    Sink filling makes every depression perfectly flat, and a perfectly flat
    area has no steepest-descent direction — so D8 routing stalls, every flat
    cell becomes its own outlet, and flow accumulation comes out *low* inside
    depressions. That is backwards: dips are where water collects, and the whole
    point of this module is to find dips.

    The fix is to put a barely-there bowl shape back:

        routing = filled - epsilon x depression_depth

    With epsilon at 0.001 the adjustment is under a millimetre, far too small to
    distort any real gradient, but enough to give every cell in a filled hollow
    a direction to send water — inward, toward the low point. Water then
    accumulates at the bottom of the dip, which is what actually happens.

    Caught by a unit test (`tests/test_terrain.py::test_twi_higher_in_dip`)
    after a first version routed on the filled surface directly and reported
    lower wetness inside a 40 cm bowl than on the plane around it.
    """
    if filled is None:
        filled = fill_depressions(dem)
    depth = np.where(np.isfinite(filled - dem), filled - dem, 0.0)
    return (filled - epsilon * depth).astype("float32")


def d8_receivers(filled: np.ndarray, cellsize_m: float):
    """For every cell, which neighbour does its water go to.

    Returns a flat array where `recv[i]` is the index of the cell downstream of
    `i`, or `i` itself for an outlet (nothing lower nearby). Steepest descent,
    corrected for the fact that a diagonal neighbour is 1.41 cells away rather
    than one.
    """
    h, w = filled.shape
    z = filled
    n = h * w
    best_drop = np.zeros((h, w), dtype="float32")
    recv = np.arange(n, dtype="int64").reshape(h, w)

    for dr, dc in _D8_OFFSETS:
        dist = cellsize_m * math.hypot(dr, dc)
        shifted = np.full_like(z, np.nan)
        src_r = slice(max(0, dr), h + min(0, dr))
        src_c = slice(max(0, dc), w + min(0, dc))
        dst_r = slice(max(0, -dr), h + min(0, -dr))
        dst_c = slice(max(0, -dc), w + min(0, -dc))
        shifted[dst_r, dst_c] = z[src_r, src_c]

        drop = (z - shifted) / dist
        drop = np.where(np.isfinite(drop), drop, -np.inf)

        idx = np.arange(n, dtype="int64").reshape(h, w)
        neighbour_idx = np.full((h, w), -1, dtype="int64")
        neighbour_idx[dst_r, dst_c] = idx[src_r, src_c]

        take = (drop > best_drop) & (neighbour_idx >= 0)
        best_drop = np.where(take, drop, best_drop)
        recv = np.where(take, neighbour_idx, recv)

    recv = recv.ravel()
    valid = np.isfinite(z).ravel()
    recv[~valid] = np.arange(n)[~valid]
    return recv, valid


def flow_accumulation(filled: np.ndarray, cellsize_m: float,
                      max_iterations: Optional[int] = None,
                      verbose: bool = True) -> Tuple[np.ndarray, Dict]:
    """How many cells drain through each cell.

    Solved as a fixed point rather than by walking the network:

        acc = 1 + (sum of acc over the cells that drain into me)

    Water only moves downhill, so the flow graph has no cycles and this
    iteration converges *exactly* — after as many rounds as the longest flow
    path is long. Each round is one sparse matrix-vector product, which numpy
    and scipy do quickly; the alternative, a Python loop over sixteen million
    cells in elevation order, would take an hour.

    Returns the accumulation grid and a small report including whether it
    actually converged, because a silent early stop would understate every
    catchment downstream.
    """
    from scipy.sparse import csr_matrix

    cfg = load_config()["terrain"]["routing"]
    max_it = max_iterations or cfg["max_iterations"]

    h, w = filled.shape
    recv, valid = d8_receivers(filled, cellsize_m)
    n = h * w
    idx = np.arange(n, dtype="int64")

    # donors[j, i] = 1 when i flows into j. Self-loops (outlets) are dropped so
    # a cell never feeds itself.
    moving = valid & (recv != idx)
    donors = csr_matrix(
        (np.ones(moving.sum(), dtype="float32"), (recv[moving], idx[moving])),
        shape=(n, n),
    )

    acc = valid.astype("float32")
    converged_at = None
    for it in range(1, max_it + 1):
        nxt = valid.astype("float32") + donors.dot(acc)
        delta = float(np.abs(nxt - acc).max())
        acc = nxt
        if delta <= cfg["convergence_tol"]:
            converged_at = it
            break
        if verbose and it % 100 == 0:
            print(f"    flow accumulation: iteration {it}, max change {delta:,.0f}")

    report = {
        "iterations": converged_at or max_it,
        "converged": converged_at is not None,
        "cells": int(valid.sum()),
        "max_accumulation_cells": float(acc.max()),
        "cellsize_m": cellsize_m,
    }
    if verbose and not report["converged"]:
        print(f"    WARNING: flow accumulation did not converge in {max_it} "
              f"iterations. Long flow paths are underestimated - raise "
              f"terrain.routing.max_iterations.")

    acc = np.where(valid, acc, np.nan).reshape(h, w).astype("float32")
    return acc, report


def topographic_wetness_index(acc: np.ndarray, slope_deg: np.ndarray,
                              cellsize_m: float) -> np.ndarray:
    """TWI = ln( upslope area per unit width / tan(slope) ).

    High where a lot of land drains into somewhere flat. A standard hydrological
    index — and one to read with real caution here.

    **Why TWI is the weakest feature in this module.** TWI describes where water
    would pool if it flowed over bare ground. Bangkok's water does not: it goes
    into pipes, canals, and pumping stations, on a network built specifically to
    override the natural surface. Without the drainage network (BMA request #3
    in the spec) TWI describes a city that is not there. It is computed because
    the spec lists it and because it may still capture something real about
    which places collect water, but if it turns out to carry no signal in
    notebook 07, that is the expected result, not a bug.
    """
    a = np.where(np.isfinite(acc), acc, np.nan) * cellsize_m  # area per unit width
    tan_b = np.tan(np.radians(np.maximum(slope_deg, 0.05)))   # floor: flat is not zero-slope
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.log(np.maximum(a, 1e-6) / tan_b).astype("float32")


# ---------------------------------------------------------------------------
# Summarising
# ---------------------------------------------------------------------------
def summarise(values: np.ndarray, prefix: str,
              percentiles: Optional[Iterable[int]] = None) -> Dict[str, float]:
    """Mean / std / percentiles of a grid, ignoring NaN, with a name prefix."""
    cfg = load_config()["terrain"]
    pcts = list(percentiles or cfg["percentiles"])
    v = values[np.isfinite(values)]
    if v.size == 0:
        out = {f"{prefix}_mean": np.nan, f"{prefix}_std": np.nan}
        out.update({f"{prefix}_p{p}": np.nan for p in pcts})
        return out
    qs = np.percentile(v, pcts)
    out = {f"{prefix}_mean": float(v.mean()), f"{prefix}_std": float(v.std())}
    out.update({f"{prefix}_p{p}": float(q) for p, q in zip(pcts, qs)})
    return out


class Histogram:
    """A running histogram, so percentiles never need the whole district in RAM.

    Nong Chok is 236 km2. At 1 m that is 236 million values — nearly a gigabyte
    just to hold them, before any of the three copies that sink filling needs.
    Binning as we go keeps memory flat regardless of district size, and 1 cm
    bins give percentiles accurate to a centimetre, which is far finer than
    anything downstream can use.
    """

    def __init__(self, lo: float, hi: float, bin_width: float):
        self.lo, self.hi, self.bw = lo, hi, bin_width
        self.edges = np.arange(lo, hi + bin_width, bin_width)
        self.counts = np.zeros(len(self.edges) - 1, dtype="int64")
        self.n = 0
        self.total = 0.0
        self.total_sq = 0.0
        self.vmin = np.inf
        self.vmax = -np.inf

    def update(self, values: np.ndarray) -> None:
        v = values[np.isfinite(values)]
        if v.size == 0:
            return
        self.counts += np.histogram(v, bins=self.edges)[0]
        self.n += v.size
        self.total += float(v.sum())
        self.total_sq += float((v.astype("float64") ** 2).sum())
        self.vmin = min(self.vmin, float(v.min()))
        self.vmax = max(self.vmax, float(v.max()))

    def percentile(self, p: float) -> float:
        if self.n == 0:
            return float("nan")
        target = p / 100.0 * self.n
        cum = np.cumsum(self.counts)
        i = int(np.searchsorted(cum, target))
        i = min(i, len(self.counts) - 1)
        return float(self.edges[i] + self.bw / 2)

    def stats(self, prefix: str, percentiles: Iterable[int]) -> Dict[str, float]:
        if self.n == 0:
            out = {f"{prefix}_{k}": np.nan for k in ("mean", "std", "min", "max")}
            out.update({f"{prefix}_p{p}": np.nan for p in percentiles})
            out[f"{prefix}_n"] = 0
            return out
        mean = self.total / self.n
        var = max(0.0, self.total_sq / self.n - mean ** 2)
        out = {f"{prefix}_mean": mean, f"{prefix}_std": math.sqrt(var),
               f"{prefix}_min": self.vmin, f"{prefix}_max": self.vmax,
               f"{prefix}_n": self.n}
        out.update({f"{prefix}_p{p}": self.percentile(p) for p in percentiles})
        return out


def district_terrain(geometry, name: str, src=None,
                     write_raster_to: Optional[str] = None,
                     restrict_to_ground: Optional[bool] = None,
                     roads=None,
                     verbose: bool = True) -> Dict[str, float]:
    """Local terrain statistics for one district, at the full 1 m.

    Reads the district in overlapping tiles, fills depressions in each, and
    keeps only the core of every tile so nothing is counted twice. The overlap
    means a dip that straddles a tile edge is still seen whole — up to the size
    of the overlap. Genuinely large basins are underestimated, and
    `depression_truncated_share` below reports how often that limit was reached
    rather than leaving you to wonder.
    """
    _require_rasterio()
    from rasterio.features import geometry_mask

    cfg = load_config()["terrain"]
    loc = cfg["local"]
    pcts = cfg["percentiles"]
    gm_cfg = cfg.get("ground_mask", {})
    use_ground = (gm_cfg.get("enabled", False) if restrict_to_ground is None
                  else restrict_to_ground)

    close_after = src is None
    src = src or rasterio.open(dtm_path())
    try:
        minx, miny, maxx, maxy = geometry.bounds
        b = loc["buffer_m"]
        patch_bounds = (minx - b, miny - b, maxx + b, maxy + b)

        # Read once to learn the shape, then work tile by tile off the file.
        probe = read_patch(patch_bounds, resolution_m=loc["resolution_m"], src=src)
        h, w = probe.dem.shape
        del probe

        elev = Histogram(-15.0, 25.0, 0.01)
        depth = Histogram(0.0, 5.0, 0.01)
        slope = Histogram(0.0, 45.0, 0.01)
        area_cells = 0
        valid_cells = 0
        depressed_cells = 0
        truncated = 0

        raster_out = None
        if write_raster_to:
            raster_out = np.full((h, w), np.nan, dtype="float32")

        win = from_bounds(*patch_bounds, transform=src.transform)
        win = win.round_offsets().round_lengths().intersection(
            Window(0, 0, src.width, src.height))
        base_transform = src.window_transform(win)

        n_tiles = 0
        for rs, cs, core in iter_tiles(h, w, loc["tile_px"], loc["tile_overlap_px"]):
            sub = Window(win.col_off + cs.start, win.row_off + rs.start,
                         cs.stop - cs.start, rs.stop - rs.start)
            dem = src.read(1, window=sub).astype("float32")
            valid = np.isfinite(dem)
            if src.nodata is not None:
                valid &= dem != src.nodata
            valid &= (dem > -100) & (dem < 500)
            dem = np.where(valid, dem, np.nan)
            if not valid.any():
                continue
            n_tiles += 1

            # Restrict to the real ground surface BEFORE filling depressions.
            # Order matters: filling a raster that still contains interpolated
            # building domes measures street canyons against rooftops, which is
            # how a 30 cm road dip became a 1.9 m "depression" in Phase 1.
            #
            # ROADS *AND* GROUND, not roads OR ground. Measured on Bang Rak:
            #
            #     no mask                  4.54 m
            #     roads only (3-15 m buf)  3.77 - 4.31 m   barely helps
            #     ground only              1.72 m
            #     roads AND ground         1.56 m          stable across buffers
            #
            # Roads alone fail because the contamination is NOT confined to
            # building footprints, which an earlier version of this comment
            # claimed. The interpolated fill bleeds across narrow streets, so a
            # buffer around a road centreline still lands on the shoulder of a
            # dome. Only the local-minimum test removes that.
            #
            # Roads still earn their place: they guarantee the surviving cells
            # are on a road rather than in a canal or a car park, which is what
            # `Flood Depth = Water Level - Road Elevation` actually needs. The
            # ground mask alone cannot tell those apart.
            tile_transform_pre = src.window_transform(sub)
            gmask = np.ones(dem.shape, dtype=bool)
            parts = []
            if use_ground:
                gmask &= ground_mask(dem, loc["resolution_m"])
                parts.append("ground")
            if roads is not None:
                rm = road_mask(geometry, dem.shape, tile_transform_pre, roads)
                if rm.any():
                    gmask &= rm
                    parts.append("roads")
            mask_source = "+".join(parts) if parts else "none"
            dem = np.where(gmask, dem, np.nan)
            valid = valid & gmask

            filled = fill_depressions(dem)
            d = depression_depth(dem, filled)
            s = slope_degrees(dem, loc["resolution_m"])

            # Keep only this tile's core, and only what is inside the district.
            tile_transform = src.window_transform(sub)
            inside = ~geometry_mask([geometry], out_shape=dem.shape,
                                    transform=tile_transform, invert=False)
            keep = np.zeros(dem.shape, dtype=bool)
            keep[core] = True
            keep &= inside

            area_cells += int(keep.sum())
            m = keep & valid
            valid_cells += int(m.sum())
            elev.update(dem[m])
            depth.update(d[m])
            slope.update(s[m])
            depressed_cells += int((d[m] >= cfg["min_depression_depth_m"]).sum())
            # A depression that reaches the tile edge was cut off by tiling.
            edge = np.zeros(dem.shape, dtype=bool)
            edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
            truncated += int((edge & m & (d >= cfg["min_depression_depth_m"])).sum())

            if raster_out is not None:
                raster_out[rs, cs][core] = np.where(keep[core], d[core], np.nan)

        row: Dict[str, float] = {"district": name}
        row.update(elev.stats("elev_m", pcts))
        row.update(depth.stats("depression_depth_m", pcts))
        row.update(slope.stats("slope_deg", pcts))
        row["area_km2"] = area_cells * (loc["resolution_m"] ** 2) / 1e6
        row["dtm_coverage_pct"] = round(100 * valid_cells / max(area_cells, 1), 2)
        row["depressed_area_share"] = round(depressed_cells / max(valid_cells, 1), 4)
        row["depression_truncated_share"] = round(truncated / max(depressed_cells, 1), 5)
        row["tiles"] = n_tiles
        row["mask"] = mask_source if n_tiles else "none"
        row["ground_share"] = round(valid_cells / max(area_cells, 1), 4)
        # A mask that keeps almost nothing has collapsed onto canal beds rather
        # than found streets. Flag it rather than quietly reporting the number.
        row["mask_suspect"] = bool(
            use_ground and row["ground_share"] < gm_cfg.get("min_ground_share", 0.01))

        if raster_out is not None and write_raster_to:
            _write_raster(raster_out, base_transform, src.crs, write_raster_to)
            row["raster"] = write_raster_to

        if verbose:
            print(f"  {name:<22} {row['area_km2']:>7.1f} km2  "
                  f"coverage {row['dtm_coverage_pct']:>5.1f}%  "
                  f"median elev {row.get('elev_m_p50', float('nan')):>5.2f} m  "
                  f"dips {100 * row['depressed_area_share']:>5.1f}% of area", flush=True)
        return row
    finally:
        if close_after:
            src.close()


def _write_raster(arr: np.ndarray, transform, crs, path: str) -> None:
    from pathlib import Path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1],
        count=1, dtype="float32", crs=crs, transform=transform,
        nodata=np.nan, compress="deflate", tiled=True,
        blockxsize=512, blockysize=512,
    ) as dst:
        dst.write(arr, 1)
        dst.build_overviews([2, 4, 8, 16, 32])


def sample_points(points: pd.DataFrame, rasters: Dict[str, Tuple[np.ndarray, "Affine"]],
                  radius_m: Optional[Iterable[float]] = None,
                  x_col: str = "x", y_col: str = "y") -> pd.DataFrame:
    """Sample terrain around a set of points. **For real coordinates only.**

    Deliberately samples a *neighbourhood* rather than the single pixel under
    the point, for two reasons. A lone 1 m pixel is noise — it might be a kerb,
    a manhole cover, or a parked lorry the survey caught. And a sensor's
    position is known to a few metres at best, so the question "what is the
    terrain around here" is answerable while "what is the terrain at exactly
    this pixel" is not.

    **This function must not be pointed at `station_registry_full.csv` as it
    stands.** Every coordinate in that file is a district centroid: all 107
    flood sensors in a district share one point, so sampling would return the
    same terrain for all of them and hand the model a fabricated feature that
    looks real. `config.terrain.point_sampling.require_coord_quality` names the
    qualities that are allowed through; `district_centroid` is not one of them.
    The function exists now so that the day coordinates arrive, Phase 1 is a
    re-run rather than a rewrite.
    """
    cfg = load_config()["terrain"]["point_sampling"]
    radii = list(radius_m or cfg["radius_m"])
    rows = []
    for _, pt in points.iterrows():
        rec = {c: pt[c] for c in points.columns if c not in (x_col, y_col)}
        rec[x_col], rec[y_col] = pt[x_col], pt[y_col]
        for name, (arr, transform) in rasters.items():
            inv = ~transform
            col, row = inv * (pt[x_col], pt[y_col])
            col, row = int(col), int(row)
            for r in radii:
                px = max(1, int(round(r / abs(transform.a))))
                r0, r1 = max(0, row - px), min(arr.shape[0], row + px + 1)
                c0, c1 = max(0, col - px), min(arr.shape[1], col + px + 1)
                block = arr[r0:r1, c0:c1]
                block = block[np.isfinite(block)]
                rec[f"{name}_mean_{int(r)}m"] = float(block.mean()) if block.size else np.nan
                rec[f"{name}_min_{int(r)}m"] = float(block.min()) if block.size else np.nan
                rec[f"{name}_max_{int(r)}m"] = float(block.max()) if block.size else np.nan
        rows.append(rec)
    return pd.DataFrame(rows)
