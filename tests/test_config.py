"""
The config contract.

WHY THIS EXISTS. `external.open_meteo.forecast.model` was renamed to `models`
when the two ECMWF archives turned out to be complementary and had to be
spliced. The library handled both spellings; notebook 04 did not, and died on
cell 3 with `KeyError: 'model'` — after the notebook had been opened, the kernel
started, and the setup run.

`config.yaml` is the single source of truth for this whole project, which means a
rename in it can break code anywhere. These tests assert the keys that code and
notebooks actually read, so that breakage surfaces in a one-second `pytest` run
instead of in the middle of a notebook.

Add a test here whenever something starts depending on a new config key.
"""

import pytest

from bkkflood.config import load_config


@pytest.fixture(scope="module")
def cfg():
    return load_config()


# ---------------------------------------------------------------------------
# Structure that everything depends on
# ---------------------------------------------------------------------------
def test_top_level_sections_present(cfg):
    for key in ("paths", "data", "exclusions", "flood_event", "horizons_hours",
                "splits", "objective", "alerting", "terrain", "external",
                "compute"):
        assert key in cfg, f"config.yaml is missing the '{key}' section"


def test_paths_resolve_to_something(cfg):
    for key in ("interim", "features", "external", "reports", "districts",
                "subdistricts", "station_registry", "dtm_1m"):
        assert key in cfg["paths"], f"paths.{key} is missing"


def test_every_raw_dataset_has_a_schema(cfg):
    for ds in ("rain", "water", "flow", "flood"):
        assert ds in cfg["paths"]["raw"], f"paths.raw.{ds} missing"
        schema = cfg["data"]["schema"][ds]
        for field in ("code", "name", "values"):
            assert field in schema, f"data.schema.{ds}.{field} missing"
        assert schema["values"], f"data.schema.{ds}.values is empty"


# ---------------------------------------------------------------------------
# The flood definition — these numbers decide every metric in the project
# ---------------------------------------------------------------------------
def test_flood_event_rules_are_sane(cfg):
    ev = cfg["flood_event"]
    tiers = ev["tiers_cm"]
    assert set(tiers) == {"nuisance", "advisory", "severe"}
    assert tiers["nuisance"] < tiers["advisory"] < tiers["severe"]
    assert ev["primary_tier_cm"] in tiers.values()
    assert ev["persistence_readings"] >= 2, (
        "one reading above a tier is a splash, not a flood — see notebook 02"
    )
    assert ev["min_event_minutes"] >= (
        ev["persistence_readings"] * cfg["data"]["cadence_minutes"]
    ), "the minimum duration must not discard events the persistence rule keeps"


def test_splits_are_chronological_and_disjoint(cfg):
    """A leak here would inflate every score in the project by 20-30 points."""
    for fold in cfg["splits"]["folds"]:
        train, val, test = fold["train"], fold["val"], fold["test"]
        assert max(train) < val < test, f"fold is not chronological: {fold}"
        assert val not in train and test not in train, f"fold leaks: {fold}"


# ---------------------------------------------------------------------------
# Alerting — the one setting that can send a real public warning
# ---------------------------------------------------------------------------
def test_cap_status_is_not_actual(cfg):
    """Flipping this to Actual publishes alerts from an experimental model.

    It requires written BMA authorisation and a named accountable owner. If this
    test ever fails, that conversation has either happened or been skipped, and
    the person changing it should have to delete this test on purpose.
    """
    assert cfg["alerting"]["cap_status"] in ("Test", "Exercise", "Draft"), (
        "cap_status must not be 'Actual' without written BMA authorisation"
    )


# ---------------------------------------------------------------------------
# External data — the keys notebook 04 reads
# ---------------------------------------------------------------------------
def test_forecast_models_is_a_nonempty_list(cfg):
    """The rename that broke notebook 04 mid-run."""
    fc = cfg["external"]["open_meteo"]["forecast"]
    assert "models" in fc, (
        "external.open_meteo.forecast.models is missing. It was renamed from "
        "'model' when the two ECMWF archives had to be spliced — notebook 04 "
        "reads 'models'."
    )
    assert isinstance(fc["models"], list) and fc["models"], (
        "models must be a non-empty list, oldest archive first"
    )


def test_forecast_model_names_are_valid(cfg):
    """Guards the two settings that have already cost a round trip each."""
    models = cfg["external"]["open_meteo"]["forecast"]["models"]

    assert "ecmwf_ifs_hres" not in models, (
        "ecmwf_ifs_hres is not a valid Open-Meteo slug — every request returns "
        "400 and the whole forecast pull comes back empty"
    )
    for bad in (None, "best_match"):
        assert bad not in models, (
            f"{bad!r} makes the historical-forecast endpoint serve the ERA5 "
            "reanalysis instead of an archived forecast. It looks healthy and "
            "it is the answer sheet — see docs/reports/phase1_2_findings.md §2"
        )


def test_forecast_and_observed_use_different_endpoints(cfg):
    """Same host for both would mean the same data under two filenames."""
    om = cfg["external"]["open_meteo"]
    assert om["forecast"]["url"] != om["observed"]["url"]
    assert om["forecast"]["out"] != om["observed"]["out"]
    assert om["forecast"]["role"] == "forecast"
    assert om["observed"]["role"] == "observed"


def test_pumps_portal_is_still_blocked(cfg):
    """No collector may be written for it until BMA gives permission."""
    blocked = cfg["external"].get("blocked_pending_permission", [])
    assert any("pumps.bangkok.go.th" in b for b in blocked)


# ---------------------------------------------------------------------------
# Terrain — the keys notebook 03 reads
# ---------------------------------------------------------------------------
def test_terrain_keys_notebook_03_uses(cfg):
    t = cfg["terrain"]
    for key in ("local", "routing", "min_depression_depth_m", "percentiles",
                "outputs", "point_sampling", "district_name_aliases"):
        assert key in t, f"terrain.{key} is missing"
    assert t["local"]["resolution_m"] == 1.0, (
        "local terrain must stay at 1 m — coarsening averages away the 20-50 cm "
        "road dips this whole phase exists to find"
    )
    assert t["local"]["tile_px"] > 2 * t["local"]["tile_overlap_px"]


def test_point_sampling_refuses_district_centroids(cfg):
    """Every coordinate we hold is a district centroid.

    Sampling terrain at one would return an identical number for every sensor in
    the district and hand the model a fabricated per-station feature.
    """
    allowed = cfg["terrain"]["point_sampling"]["require_coord_quality"]
    assert "district_centroid" not in allowed
    assert "none" not in allowed


def test_era5_is_never_a_model_feature():
    """ERA5 is reanalysis, published ~5 days late.

    In the feature table it is legitimate past rain. As a MODEL input it is
    training/serving skew: populated offline, NaN in production. It is worth a
    fifth of the onset model's PR-AUC (0.160 -> 0.129), which is exactly why the
    exclusion needs a test rather than a good intention.
    """
    from bkkflood.models import feature_set
    cols = ["fl_depth_now", "rain_rf1hr_mean", "era5_rain_3h",
            "rain_fcst_3h", "y_ge15_1h", "station_code", "ts"]
    for kind in ("general", "onset", "depth"):
        for years in ([2019, 2020], [2021, 2022, 2023]):
            got = feature_set(cols, kind, years)
            assert not any(c.startswith("era5") for c in got), (kind, years, got)


def test_forecast_rain_only_reaches_the_onset_model():
    """Measured Phase 3: GFS improves onset PR-AUC 24% and degrades all-rows 24%."""
    from bkkflood.models import feature_set
    cols = ["fl_depth_now", "rain_fcst_3h", "rain_rf1hr_mean"]
    assert "rain_fcst_3h" in feature_set(cols, "onset", [2021, 2022])
    assert "rain_fcst_3h" not in feature_set(cols, "general", [2021, 2022])
    # ...and never on a fold that predates the archive, whatever the model kind.
    assert "rain_fcst_3h" not in feature_set(cols, "onset", [2019, 2020])
