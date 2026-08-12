"""
Unit tests for the terrain maths.

These run on tiny synthetic surfaces where the right answer is known by
construction — a plane with a known grade, a bowl of a known depth. They take
about a second and need no data files, so there is no excuse not to run them
before trusting a number that came out of a 13.9 GB raster.

    pytest tests/ -v

Every test here exists because it caught something, or because it guards a
result that would be silently wrong rather than loudly broken.
"""

import numpy as np
import pytest

from bkkflood.terrain import (
    Histogram,
    ground_mask,
    d8_receivers,
    depression_depth,
    fill_depressions,
    flow_accumulation,
    routing_surface,
    slope_degrees,
    topographic_wetness_index,
)

GRADE = 0.01          # 1% slope, i.e. 1 cm drop per metre
BOWL_DEPTH = 0.40     # a 40 cm dip, the scale of a real Bangkok road hollow


@pytest.fixture
def terrain():
    """A plane tilted 1% to the east, with one 40 cm bowl punched into it."""
    h = w = 60
    y, x = np.mgrid[0:h, 0:w]
    dem = (2.0 - GRADE * x).astype("float32")
    bowl = ((x - 30) ** 2 + (y - 30) ** 2) < 8 ** 2
    dem[bowl] -= BOWL_DEPTH
    return dem, bowl


def test_depression_depth_finds_the_bowl(terrain):
    dem, bowl = terrain
    depth = depression_depth(dem, min_depth_m=0.0)
    assert 0.30 < np.nanmax(depth) <= BOWL_DEPTH + 0.01


def test_depression_depth_is_zero_on_open_ground(terrain):
    """A slope is not a dip. If this fails, every district looks flooded."""
    dem, bowl = terrain
    depth = depression_depth(dem, min_depth_m=0.0)
    assert np.nanmax(depth[~bowl]) < 0.02


def test_slope_matches_a_known_grade(terrain):
    """1% grade is 0.5729 degrees. Guards against a metres/pixels mix-up."""
    dem, bowl = terrain
    s = slope_degrees(dem, cellsize_m=1.0)
    interior = s[5:-5, 5:-5][~bowl[5:-5, 5:-5]]
    assert abs(float(np.median(interior)) - 0.5729) < 0.05


def test_nodata_is_an_outlet_not_a_cliff(terrain):
    """The DTM is a rectangle with a city-shaped hole of real data in it.

    53% of the file is nodata — everything outside the BMA boundary. If that
    were treated as elevation zero, the whole city would look like it sits on a
    plateau and every boundary district would be one enormous depression.
    """
    dem, _ = terrain
    dem = dem.copy()
    dem[:, :10] = np.nan
    depth = depression_depth(dem, min_depth_m=0.0)
    assert np.all(np.isnan(depth[:, :10]))
    assert np.nanmax(depth[:, 10:]) <= BOWL_DEPTH + 0.01


def test_flow_accumulation_converges_on_a_plane():
    """On a pure plane every row drains one way; the far column collects them."""
    h, w = 60, 60
    _, x = np.mgrid[0:h, 0:w]
    plane = (2.0 - GRADE * x).astype("float32")
    acc, report = flow_accumulation(plane, cellsize_m=1.0, verbose=False)
    assert report["converged"], "did not converge - raise max_iterations"
    assert 50 <= report["max_accumulation_cells"] <= 80


def test_receivers_point_downhill():
    h, w = 20, 20
    _, x = np.mgrid[0:h, 0:w]
    plane = (2.0 - GRADE * x).astype("float32")
    recv, valid = d8_receivers(plane, cellsize_m=1.0)
    z = plane.ravel()
    moving = valid & (recv != np.arange(recv.size))
    assert np.all(z[recv[moving]] <= z[moving])


def test_twi_higher_in_dip(terrain):
    """THE REGRESSION TEST.

    The first version of this module routed water over the sink-filled surface.
    Filling makes a depression perfectly flat, a flat has no downhill direction,
    D8 stalls, and wetness came out *lower* inside a 40 cm bowl than on the open
    plane around it — precisely backwards, and precisely in the places this whole
    module exists to find. `routing_surface()` restores a sub-millimetre bowl
    shape so water routes inward again.
    """
    dem, bowl = terrain
    filled = fill_depressions(dem)
    surface = routing_surface(dem, filled)
    acc, _ = flow_accumulation(surface, cellsize_m=1.0, verbose=False)
    twi = topographic_wetness_index(acc, slope_degrees(surface, 1.0), 1.0)
    assert np.isfinite(twi).all()
    assert float(np.nanmean(twi[bowl])) > float(np.nanmean(twi[~bowl])), (
        "wetness index is lower inside the dip - routing surface is wrong"
    )


def test_histogram_percentiles_match_numpy():
    """Districts are too big to hold in memory, so percentiles come from a
    running histogram. It has to agree with the real thing to a centimetre."""
    rng = np.random.default_rng(0)
    values = rng.normal(1.0, 0.3, 500_000).astype("float32")
    hist = Histogram(-15.0, 25.0, 0.01)
    for chunk in np.array_split(values, 7):
        hist.update(chunk)
    for p in (1, 5, 25, 50, 75, 95, 99):
        assert abs(hist.percentile(p) - float(np.percentile(values, p))) < 0.02
    assert abs(hist.total / hist.n - float(values.mean())) < 1e-3


def test_histogram_handles_nothing():
    hist = Histogram(0.0, 5.0, 0.01)
    hist.update(np.array([np.nan, np.nan], dtype="float32"))
    assert hist.n == 0
    assert np.isnan(hist.percentile(50))


# ---------------------------------------------------------------------------
# Phase 1.5 — recovering ground from a DTM that includes interpolated buildings
# ---------------------------------------------------------------------------
@pytest.fixture
def contaminated():
    """A street grid with interpolated "building" domes sitting on top of it.

    This reproduces what DTM_1M actually contains in dense districts: true ground
    near 1 m, smooth mounds rising toward roof height over building footprints,
    and narrow streets between them.

    Two details matter and the first version of this fixture got both wrong.
    The domes have to cover enough area that the *median* is roof-level — that is
    the symptom (Pathum Wan reads 4.57 m). And the streets have to be enclosed,
    or they drain off the tile edge and no depressions form at all, which is not
    what happens inside a real city block.
    """
    h = w = 240
    dem = np.full((h, w), 1.0, dtype="float32")
    dem[118:122, 118:122] -= 0.30                       # a 30 cm road dip

    # 50 m blocks on a 60 m grid: narrow streets, domes covering most of the area
    for by in range(0, h, 60):
        for bx in range(0, w, 60):
            yy, xx = np.mgrid[0:50, 0:50]
            r = np.hypot(yy - 25, xx - 25) / 25.0
            dome = 3.5 * np.clip(1 - r ** 2, 0, 1)
            sl = (slice(by, min(by + 50, h)), slice(bx, min(bx + 50, w)))
            dem[sl] += dome[:sl[0].stop - sl[0].start, :sl[1].stop - sl[1].start]

    dem[:4, :] = dem[-4:, :] = dem[:, :4] = dem[:, -4:] = 5.0   # enclose the grid
    return dem


def test_ground_mask_recovers_true_ground(contaminated):
    """The headline fix: median elevation must come back to real ground."""
    before = float(np.median(contaminated))
    mask = ground_mask(contaminated, cellsize_m=1.0, window_m=100, tolerance_m=1.0)
    after = float(np.median(contaminated[mask]))
    assert before > 1.5, "fixture is not contaminated enough to be a test"
    assert abs(after - 1.0) < 0.35, (
        f"ground should come back near 1.0 m, got {after:.2f} (was {before:.2f})"
    )


def test_ground_mask_excludes_the_domes(contaminated):
    """Whatever it keeps must not be roof."""
    mask = ground_mask(contaminated, cellsize_m=1.0, window_m=100, tolerance_m=1.0)
    assert contaminated[mask].max() < 2.5


def test_ground_mask_keeps_a_plausible_share(contaminated):
    """Too little and it has collapsed onto the single lowest point."""
    mask = ground_mask(contaminated, cellsize_m=1.0, window_m=100, tolerance_m=1.0)
    assert 0.05 < mask.mean() < 0.80


def test_ground_mask_leaves_open_ground_alone():
    """THE CONTROL, and the one that constrains the window size.

    On genuinely bare terrain the mask must barely change anything. Past about a
    150 m window it stops finding streets and starts finding the lowest point in
    a large area, which on real data pushed open Lat Krabang below zero — canal
    bed, not ground.
    """
    h = w = 240
    y, x = np.mgrid[0:h, 0:w]
    open_ground = (0.8 + 0.002 * x).astype("float32")   # a gentle real slope
    before = float(np.median(open_ground))
    mask = ground_mask(open_ground, cellsize_m=1.0, window_m=100, tolerance_m=1.0)
    after = float(np.median(open_ground[mask]))
    assert mask.mean() > 0.30, "should keep most of an open district"
    assert abs(after - before) < 0.25, (
        f"open ground moved {before:.2f} -> {after:.2f}; the window is too wide"
    )


def test_depression_depth_is_comparable_after_masking(contaminated):
    """Why this matters for the model, not just for the map.

    Unmasked, a street between two roof-height domes reads as a ~2 m depression
    while the same 30 cm dip in an open district reads as 0.3 m. The feature
    means different things in different places, which makes it useless. Masking
    makes it measure one thing everywhere.
    """
    unmasked = depression_depth(contaminated, min_depth_m=0.0)
    mask = ground_mask(contaminated, cellsize_m=1.0, window_m=100, tolerance_m=1.0)
    masked = depression_depth(np.where(mask, contaminated, np.nan), min_depth_m=0.0)
    assert np.nanpercentile(unmasked, 95) > 1.0, "fixture should look contaminated"
    assert np.nanpercentile(masked, 95) < 0.6, (
        "after masking, depressions should be road-dip scale, not building scale"
    )
