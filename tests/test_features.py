"""Fast guards on the feature builder. No data files; runs in milliseconds."""

import pandas as pd
import pytest

from bkkflood.features import feature_columns, _CALENDAR_SQL, M2_HOURS, SYNODIC_DAYS


def test_feature_columns_excludes_labels_and_keys():
    df = pd.DataFrame(columns=[
        "station_code", "ts", "district", "district_code", "terr_granularity",
        "fl_depth_now", "rain_rf1hr_mean",
        "y_maxdepth_1h", "y_ge15_1h", "y_valid_1h", "is_onset_15_1h"])
    cols = feature_columns(df)
    assert cols == ["fl_depth_now", "rain_rf1hr_mean"]


def test_onset_flag_is_never_a_model_input():
    """`is_onset_*` is the label window's starting condition.

    It exists to split recall into onset and ongoing when reporting. If it ever
    reaches a model, the model is told whether the road was already flooded --
    which is most of the answer.
    """
    df = pd.DataFrame(columns=["is_onset_5_1h", "is_onset_15_6h", "fl_std_3h"])
    assert feature_columns(df) == ["fl_std_3h"]


def test_no_feature_column_starts_with_y():
    df = pd.DataFrame(columns=["y_anything_at_all", "rain_spread"])
    assert feature_columns(df) == ["rain_spread"]


@pytest.mark.parametrize("frag", [
    "cal_hour_sin", "cal_hour_cos", "cal_doy_sin", "cal_doy_cos",
    "cal_monsoon", "tide_m2_sin", "tide_m2_cos", "tide_spring_neap"])
def test_calendar_sql_defines_every_expected_column(frag):
    assert f"AS {frag}" in _CALENDAR_SQL


def test_tidal_constants_are_the_real_periods():
    """Wrong to a few minutes and the M2 term drifts out of phase over a year."""
    assert M2_HOURS == pytest.approx(12.4206, abs=1e-3)
    assert SYNODIC_DAYS == pytest.approx(29.5306, abs=1e-3)


def test_district_join_uses_name_not_inverted_code():
    """Regression guard for the 46.1% bug.

    97 station prefixes map onto 49 districts, because rain, water, flow and
    flood each use their own prefix for the same place. Inverting that map to
    name -> prefix keeps one arbitrary prefix per district and drops the rest;
    it cost 16 of the 33 flood districts their terrain and appeared only as a
    suspiciously round null rate in two unrelated feature blocks at once.
    """
    import inspect
    from bkkflood import features
    src = inspect.getsource(features.write_feature_table)
    assert "g.district = d.district" in src, "terrain must join on district name"
    assert "e.district = d.district" in src, "external must join on district name"
    terr_src = inspect.getsource(features._terrain_frame)
    assert "{v: k for k, v in" not in terr_src, "do not invert the prefix map"
