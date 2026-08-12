"""Tests for live feature assembly and live prediction mode."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from bkkflood.features import _FLOOD_COLS, _RAIN_COLS, _WF_COLS
from bkkflood.live import (
    LIVE_MODE, LIVE_PERFORMANCE, cold_start_check,
    live_features, live_rain_forecast, live_status, live_water_features
)
from bkkflood.serving import load_bundle, forecast_at, district_risk, _forecast_live


def test_live_features_contract():
    """Live features DataFrame must contain all columns required by trained models."""
    df = live_features()
    assert isinstance(df, pd.DataFrame)
    assert not df.empty, "expected rows for flood stations"
    assert len(df) >= 107

    # Load default model bundle to verify column match
    b = load_bundle("onset_t15_h1_final")
    for feat in b.features:
        assert feat in df.columns, f"missing required feature: {feat}"

    assert "station_code" in df.columns
    assert "district" in df.columns
    assert "ts" in df.columns


def test_live_features_nan_pattern():
    """Verify that unavailable BMA sources are NaN, while available ones are populated."""
    df = live_features()

    # All flood sensor history features must be NaN (no live road sensors)
    for col in _FLOOD_COLS:
        assert df[col].isna().all(), f"expected NaN for unavailable flood feature {col}"

    # All rain gauge features must be NaN (no live BMA rain gauges)
    for col in _RAIN_COLS:
        assert df[col].isna().all(), f"expected NaN for unavailable rain feature {col}"

    # Calendar and tide features must be fully non-NaN (pure math from timestamp)
    for col in ["cal_hour_sin", "cal_hour_cos", "cal_doy_sin", "cal_doy_cos",
                "cal_monsoon", "tide_m2_sin", "tide_m2_cos", "tide_spring_neap"]:
        assert not df[col].isna().any(), f"expected non-NaN for calendar feature {col}"

    # Terrain features should be populated for stations with known districts
    for col in ["terr_elev_m_p50", "terr_elev_m_p10", "terr_depression_depth_m_p95"]:
        if col in df.columns:
            assert df[col].notna().any(), f"expected terrain values for {col}"


def test_cold_start_check():
    """Cold start status returns expected fields."""
    cs = cold_start_check()
    assert "cold_start" in cs
    assert isinstance(cs["cold_start"], bool)
    assert "sources" in cs
    assert "minimum_hours" in cs
    assert cs["minimum_hours"] == 24


def test_live_status_structure():
    """Live status report has required mode performance and availability fields."""
    status = live_status()
    assert status["data_mode"] == LIVE_MODE
    assert status["mode_performance"]["event_pod"] == 0.049
    assert len(status["available_sources"]) >= 2
    assert len(status["missing_sources"]) >= 2
    assert len(status["features_nan"]) >= 2


def test_model_predicts_on_live_features():
    """The trained LightGBM model runs cleanly on live features with NaNs."""
    b = load_bundle("onset_t15_h1_final")
    df = live_features()

    prob = b.predict(df)
    raw = b.raw_score(df)

    assert len(prob) == len(df)
    assert len(raw) == len(df)
    assert np.all(np.isfinite(prob) | np.isnan(prob))
    assert np.all(np.isfinite(raw) | np.isnan(raw))


def test_live_forecast_at_payload():
    """Live forecast endpoint payload structure and performance metadata."""
    res = forecast_at(mode="live")
    assert res["data_mode"] == LIVE_MODE
    assert "mode_performance" in res
    assert res["mode_performance"]["event_pod"] == 0.049
    assert isinstance(res["stations"], list)
    assert len(res["stations"]) >= 107
    assert "live_note" in res

    for st in res["stations"]:
        assert st["depth_now_cm"] is None
        assert st["predicted_depth_cm"] is None
        assert st["status"] in ("at_risk", "clear")



def test_live_district_risk_payload():
    """Live district risk payload retains mode_performance and data_mode."""
    risk = district_risk(mode="live")
    assert risk["data_mode"] == LIVE_MODE
    assert risk["is_flood_extent"] is False
    assert "mode_performance" in risk
    assert isinstance(risk["districts"], list)
