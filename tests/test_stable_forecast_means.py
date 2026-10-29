"""Finite forecast error means should not fail on overflowing intermediate sums."""

from __future__ import annotations

import math
from collections.abc import Sequence

import pytest

from inventory_policy_lab import backtest, moving_average, naive
from inventory_policy_lab.forecast import naive_scale


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
