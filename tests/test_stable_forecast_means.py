"""Finite forecast error means should not fail on overflowing intermediate sums."""

from __future__ import annotations

import math
from collections.abc import Sequence

import pytest

from inventory_policy_lab import backtest, moving_average, naive
from inventory_policy_lab.forecast import naive_scale
from inventory_policy_lab.smoothing import SmoothingFit


def test_moving_average_stays_finite_when_fmean_sum_would_overflow() -> None:
    assert moving_average([1e308, 1e308], window=2) == pytest.approx(1e308)
    assert moving_average([1e308, 0.0, 1e308], window=3) == pytest.approx((2 / 3) * 1e308)


def test_naive_mase_scale_uses_representable_mean_of_large_differences() -> None:
    train = [0.0, 1e308, 0.0, 1e308]
    assert naive_scale(train) == pytest.approx(1e308)
    result = backtest([*train, 1e308], "naive", naive, holdout=1)
    assert result.mase == 0.0


def test_backtest_scoring_avoids_overflowing_mean_error_and_bias() -> None:
    # Two positive errors followed by one negative error: the mean bias is
    # finite despite an overflowing intermediate 1e308 + 1e308 sum.
    series = [0.0, 0.0, 0.0, 0.0, 0.0, 1e308]

    def method(history: Sequence[float]) -> float:
        return 1e308 if len(history) < 5 else 0.0

    result = backtest(series, "large errors", method, holdout=3)
    assert all(math.isfinite(value) for value in (result.mae, result.rmse, result.bias))
    assert result.mae == pytest.approx(1e308)
    assert result.rmse == pytest.approx(1e308)
    assert result.bias == pytest.approx(1e308 / 3)
    assert result.mase is None


def test_smoothing_mean_does_not_overflow_when_the_mean_is_finite() -> None:
    fit = SmoothingFit(
        model="holt_damped", alpha=0.2, beta=0.1, phi=0.8, gamma=None,
        level=1e308, trend=0.0, seasonals=(), sse=0.0,
    )
    assert fit.forecast(1) == 1e308
    assert fit.mean_forecast(1) == 1e308
    assert fit.mean_forecast(2) == pytest.approx(1e308)
    assert fit.mean_forecast(3) == pytest.approx(1e308)


def test_smoothing_mean_of_large_alternating_seasonal_demand_is_finite() -> None:
    fit = SmoothingFit(
        model="hw_additive", alpha=0.2, beta=0.1, phi=0.8, gamma=0.1,
        level=1e308, trend=0.0, seasonals=(0.0, -1e308), sse=0.0,
    )
    assert [fit.forecast(h) for h in range(1, 5)] == [1e308, 0.0, 1e308, 0.0]
    assert fit.mean_forecast(4) == pytest.approx(5e307)
    # Preserve the documented nonpositive-horizon clamp and normal results.
    assert fit.mean_forecast(0) == fit.forecast(1)
