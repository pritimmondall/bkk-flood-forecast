"""Metrics on hand-computable examples. No data files."""

import numpy as np
import pandas as pd
import pytest

from bkkflood.evaluate import (binary_metrics, pr_auc, brier, best_threshold,
                               by_onset, event_pod, folds)


def test_binary_metrics_on_a_case_worked_out_by_hand():
    #        y: 1 1 1 0 0
    #     pred: 1 0 1 1 0   -> tp=2 fn=1 fp=1 tn=1
    y = np.array([1, 1, 1, 0, 0], dtype=bool)
    p = np.array([1, 0, 1, 1, 0], dtype=bool)
    m = binary_metrics(y, p)
    assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (2, 1, 1, 1)
    assert m["precision"] == pytest.approx(2 / 3)
    assert m["recall"] == pytest.approx(2 / 3)
    assert m["f1"] == pytest.approx(2 / 3)
    assert m["fnr"] == pytest.approx(1 / 3)


def test_f2_weights_recall_above_precision():
    """The whole reason F2 is the primary metric.

    Same number of errors, but the model that catches more floods and cries wolf
    must score higher than the one that stays quiet and misses them.
    """
    y = np.array([1] * 10 + [0] * 90, dtype=bool)
    catches_more = np.array([1] * 9 + [0] + [1] * 9 + [0] * 81, dtype=bool)
    stays_quiet = np.array([1] * 5 + [0] * 5 + [0] * 90, dtype=bool)
    assert binary_metrics(y, catches_more)["f2"] > binary_metrics(y, stays_quiet)["f2"]
    # ...and F1 would have preferred the quiet one, which is the trap.
    assert binary_metrics(y, stays_quiet)["f1"] > binary_metrics(y, catches_more)["f1"]


def test_perfect_and_useless_predictions():
    y = np.array([1, 0, 1, 0], dtype=bool)
    assert binary_metrics(y, y)["f2"] == pytest.approx(1.0)
    none = np.zeros(4, dtype=bool)
    m = binary_metrics(y, none)
    assert m["recall"] == 0.0 and m["fnr"] == 1.0 and m["f2"] == 0.0


def test_pr_auc_of_a_perfect_ranking_is_one():
    """Regression guard.

    The first implementation integrated the PR curve with the trapezoid rule and
    scored a perfect ranking at 0.50, because precision drops vertically at each
    false positive while recall stands still and the trapezoid averages across
    the drop. Any change here that reintroduces trapezoid integration fails this.
    """
    y = np.array([1, 1, 0, 0], dtype=bool)
    assert pr_auc(y, np.array([0.9, 0.8, 0.2, 0.1])) == pytest.approx(1.0, abs=1e-6)


def test_pr_auc_of_an_exactly_reversed_ranking_is_poor():
    y = np.array([1, 1, 0, 0], dtype=bool)
    assert pr_auc(y, np.array([0.1, 0.2, 0.8, 0.9])) < 0.6


def test_pr_auc_of_random_scores_sits_near_the_base_rate():
    """The no-skill line is the base rate, NOT 0.5.

    Quoting PR-AUC without it is how 0.10 gets called poor when the base rate is
    0.0008 and it is in fact a 129-fold improvement.
    """
    rng = np.random.default_rng(0)
    y = rng.random(20000) < 0.02
    assert pr_auc(y, rng.random(20000)) == pytest.approx(0.02, abs=0.01)


def test_brier_rewards_calibration():
    y = np.array([1, 0, 1, 0], dtype=bool)
    assert brier(y, np.array([1.0, 0.0, 1.0, 0.0])) == pytest.approx(0.0)
    assert brier(y, np.array([0.5] * 4)) == pytest.approx(0.25)


def test_best_threshold_finds_the_separating_cut():
    y = np.array([0, 0, 1, 1], dtype=bool)
    s = np.array([0.1, 0.2, 0.8, 0.9])
    best = best_threshold(y, s, metric="f2")
    assert best["f2"] == pytest.approx(1.0)
    assert 0.2 < best["threshold"] <= 0.8


def test_onset_split_exposes_a_model_that_only_repeats_the_present():
    """The failure this project exists to avoid reporting.

    A model that predicts "flooded" only where it is already flooded gets 100%
    on ongoing rows, 0% on onsets, and a headline recall that hides both.
    """
    y = np.array([1, 1, 1, 1], dtype=bool)
    onset = np.array([True, True, False, False])
    pred = np.array([0, 0, 1, 1], dtype=bool)      # only the ongoing ones
    r = by_onset(y, pred, onset).set_index("subset")
    assert r.loc["overall", "recall"] == pytest.approx(0.5)
    assert r.loc["onset", "recall"] == 0.0
    assert r.loc["ongoing", "recall"] == pytest.approx(1.0)


def _event_frame(alert_offsets_min, wet_minutes=60):
    """One station; water reaches 20 cm at 12:00. Alerts at the given offsets."""
    start = pd.Timestamp("2022-06-01 12:00")
    ts = pd.date_range(start - pd.Timedelta("6h"), start + pd.Timedelta("2h"),
                       freq="15min")
    wet = (ts >= start) & (ts < start + pd.Timedelta(minutes=wet_minutes))
    return pd.DataFrame({
        "station_code": "FL.TST.01",
        "ts": ts,
        "depth": np.where(wet, 20.0, 0.0),
        "pred": ts.isin([start + pd.Timedelta(minutes=m)
                         for m in alert_offsets_min]),
    })


def test_event_pod_counts_an_early_alert_as_a_hit_with_lead_time():
    r = event_pod(_event_frame([-45]), "depth", "pred", tier_cm=15, horizon_h=1)
    assert r["events"] == 1 and r["events_detected"] == 1
    assert r["median_lead_minutes"] == pytest.approx(45.0)


def test_event_pod_does_not_credit_an_alert_that_arrives_late():
    """Catching rows 2-4 of a flood is not warning anybody.

    Row recall would call this 75%. Event POD calls it a miss, which is what an
    operations team would call it.
    """
    r = event_pod(_event_frame([15, 30, 45]), "depth", "pred", tier_cm=15, horizon_h=1)
    assert r["events_detected"] == 0 and r["event_pod"] == 0.0


def test_event_pod_ignores_an_alert_older_than_the_horizon():
    r = event_pod(_event_frame([-240]), "depth", "pred", tier_cm=15, horizon_h=1)
    assert r["events_detected"] == 0


def test_an_alert_at_the_moment_the_water_arrives_is_not_a_warning():
    """Lead time zero is detection, not warning. BMA cannot dispatch on it."""
    r = event_pod(_event_frame([0]), "depth", "pred", tier_cm=15, horizon_h=1)
    assert r["events_detected"] == 0


def test_an_alert_left_over_from_the_previous_flood_gets_no_credit():
    """The bug that gave persistence a 150-minute median lead.

    Persistence cannot fire before a road is wet. It appeared to, because an
    alert still running from an earlier flood fell inside the next event's
    lookback window and was counted as advance warning for it.
    """
    start1 = pd.Timestamp("2022-06-01 12:00")
    start2 = start1 + pd.Timedelta("3h")
    ts = pd.date_range(start1 - pd.Timedelta("2h"), start2 + pd.Timedelta("2h"),
                       freq="15min")
    wet = (((ts >= start1) & (ts < start1 + pd.Timedelta("1h"))) |
           ((ts >= start2) & (ts < start2 + pd.Timedelta("1h"))))
    df = pd.DataFrame({"station_code": "FL.TST.01", "ts": ts,
                       "depth": np.where(wet, 20.0, 0.0),
                       # fires only during the FIRST flood
                       "pred": (ts >= start1) & (ts < start1 + pd.Timedelta("1h"))})
    r = event_pod(df, "depth", "pred", tier_cm=15, horizon_h=6)
    assert r["events"] == 2
    assert r["events_detected"] == 0, "an alert from flood 1 must not warn for flood 2"


def test_folds_are_chronological_and_never_overlap():
    for f in folds():
        assert max(f["train"]) < f["val"] < f["test"], f
        assert f["test"] not in f["train"] and f["val"] not in f["train"]


def test_best_threshold_finds_a_cut_in_a_zero_inflated_score():
    """Regression guard for the degenerate-grid bug.

    Flood depth is zero in ~99% of rows. A candidate grid built from evenly
    spaced quantiles is then almost entirely 0.0 and jumps straight to the
    extreme tail, so the useful range is never tested. On the real folds this
    picked 0.0 twice (alert on everything) and 44.1 cm once (alert on nothing).

    Here the separating cut is at 0.5 while 99% of scores are exactly 0. A
    quantile-only grid cannot find it.
    """
    rng = np.random.default_rng(1)
    n = 20000
    scores = np.zeros(n)
    y = np.zeros(n, dtype=bool)
    pos = rng.choice(n, 150, replace=False)
    y[pos] = True
    scores[pos] = rng.uniform(0.6, 3.0, size=pos.size)      # positives are wet
    noise = rng.choice(np.setdiff1d(np.arange(n), pos), 150, replace=False)
    scores[noise] = rng.uniform(0.05, 0.4, size=noise.size)  # damp but dry

    best = best_threshold(y, scores, metric="f2")
    # Anywhere in the gap between the dry noise (max 0.4) and the bulk of the
    # positives. The point is that it is not 0.0 and not out in the tail.
    assert 0.4 < best["threshold"] < 0.8, best["threshold"]
    assert best["recall"] > 0.9 and best["precision"] > 0.9


def test_best_threshold_does_not_collapse_to_alerting_on_everything():
    """Alerting on every row gives recall 1.0 and must still lose on F2."""
    rng = np.random.default_rng(2)
    n = 50000
    y = rng.random(n) < 0.001
    scores = np.where(y, rng.uniform(5, 10, n), 0.0)
    best = best_threshold(y, scores, metric="f2")
    assert best["threshold"] > 0.0
    assert best["fp"] < n * 0.01
