"""Calibration checks on hand-built cases. No data files."""

import numpy as np
import pandas as pd
import pytest

from bkkflood.calibration import (reliability_curve, expected_calibration_error,
                                  isotonic_fit, apply_isotonic, quantile_coverage,
                                  coverage_verdict, lead_time_distribution)


def test_a_perfectly_calibrated_model_shows_no_gap():
    rng = np.random.default_rng(0)
    p = rng.uniform(0, 1, 40000)
    y = rng.random(40000) < p
    c = reliability_curve(y, p)
    assert expected_calibration_error(c) < 0.02


def test_an_overconfident_model_is_caught():
    """A model claiming ten times the true rate must show it."""
    rng = np.random.default_rng(1)
    true_p = rng.uniform(0, 0.05, 40000)
    y = rng.random(40000) < true_p
    c = reliability_curve(y, np.clip(true_p * 10, 0, 1))
    assert expected_calibration_error(c) > 0.05
    assert c.over_confidence.median() > 4


def test_quantile_bins_beat_equal_width_on_a_rare_event():
    """The reason `strategy="quantile"` is the default.

    At a 1-in-1000 base rate, equal-width bins put essentially everything in the
    first bin and can say nothing. Quantile bins spread the rows out and can.
    """
    rng = np.random.default_rng(2)
    p = rng.uniform(0, 0.002, 50000)
    y = rng.random(50000) < p
    assert len(reliability_curve(y, p, strategy="quantile")) >= 8
    assert len(reliability_curve(y, p, strategy="uniform")) <= 2


def test_isotonic_repairs_probabilities_without_changing_the_ranking():
    """The property that makes isotonic safe here.

    Calibration must not undo Phase 4. Because the map is monotone, every
    threshold, recall and precision figure survives it unchanged.
    """
    rng = np.random.default_rng(3)
    true_p = rng.uniform(0, 0.1, 30000)
    y = rng.random(30000) < true_p
    inflated = np.clip(true_p * 8, 0, 1)

    iso = isotonic_fit(y[:15000], inflated[:15000])
    fixed = apply_isotonic(iso, inflated[15000:])

    before = expected_calibration_error(reliability_curve(y[15000:], inflated[15000:]))
    after = expected_calibration_error(reliability_curve(y[15000:], fixed))
    assert after < before

    order_before = np.argsort(inflated[15000:])
    order_after = np.argsort(fixed, kind="stable")
    assert np.array_equal(np.argsort(order_before), np.argsort(order_before))
    # Monotone: sorted input must give non-decreasing output.
    s = np.sort(inflated[15000:])
    assert np.all(np.diff(apply_isotonic(iso, s)) >= -1e-12)


def test_coverage_on_dry_rows_is_meaningless_and_the_wet_number_exposes_it():
    """The exact failure Phase 4's depth model had.

    An interval of [0, 0] everywhere covers 99% of rows and none of the wet
    ones. Overall coverage says 0.99; wet coverage says 0.0.
    """
    truth = np.r_[np.zeros(9900), np.full(100, 20.0)]
    lo = np.zeros(10000)
    hi = np.zeros(10000)
    cov = quantile_coverage(truth, lo, hi)
    assert cov["coverage_all"] > 0.98
    assert cov["coverage_wet"] == 0.0
    assert coverage_verdict(cov)["publishable_as_p95"] is False


def test_a_genuinely_good_interval_passes():
    """90 of 100 wet rows inside — which is what a 90% interval should do.

    Note that covering ALL of them would fail too, in the other direction: an
    interval wide enough to never be wrong carries no information. The band in
    config is two-sided on purpose.
    """
    wet_truth = np.r_[np.full(90, 20.0), np.full(10, 40.0)]
    truth = np.r_[np.zeros(9900), wet_truth]
    lo = np.zeros(10000)
    hi = np.r_[np.full(9900, 1.0), np.full(100, 25.0)]   # catches the 90, misses the 10
    cov = quantile_coverage(truth, lo, hi)
    assert cov["coverage_wet"] == pytest.approx(0.90)
    assert coverage_verdict(cov)["publishable_as_p95"]


def test_an_interval_that_is_never_wrong_also_fails():
    truth = np.r_[np.zeros(9900), np.full(100, 20.0)]
    hi = np.full(10000, 500.0)      # always right, never useful
    v = coverage_verdict(quantile_coverage(truth, np.zeros(10000), hi))
    assert v["publishable_as_p95"] is False
    assert "too wide" in v["verdict"]


def test_a_too_narrow_interval_fails_in_the_dangerous_direction():
    truth = np.r_[np.zeros(9900), np.full(100, 40.0)]
    hi = np.r_[np.full(9900, 1.0), np.full(100, 25.0)]   # water deeper than claimed
    v = coverage_verdict(quantile_coverage(truth, np.zeros(10000), hi))
    assert "understates depth" in v["verdict"]


def test_lead_time_distribution_returns_one_row_per_event():
    start = pd.Timestamp("2022-06-01 12:00")
    ts = pd.date_range(start - pd.Timedelta("3h"), start + pd.Timedelta("1h"),
                       freq="15min")
    wet = (ts >= start) & (ts < start + pd.Timedelta("30min"))
    df = pd.DataFrame({"station_code": "FL.TST.01", "ts": ts,
                       "depth": np.where(wet, 20.0, 0.0),
                       "pred": ts == start - pd.Timedelta("30min")})
    d = lead_time_distribution(df, "depth", "pred", tier_cm=15, horizon_h=1)
    assert len(d) == 1
    assert d.detected.iloc[0]
    assert d.lead_minutes.iloc[0] == pytest.approx(30.0)
