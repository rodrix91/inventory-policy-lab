"""Public holdout backtests must reject corrupt actuals and forecasts."""

from __future__ import annotations

import math
from collections.abc import Sequence

import pytest

from inventory_policy_lab import backtest, naive


@pytest.mark.parametrize("invalid", [-1.0, -0.01, math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("index", [0, 2, 4])
def test_backtest_rejects_invalid_demand_anywhere(invalid: float, index: int) -> None:
    history = [3.0, 4.0, 5.0, 6.0, 7.0]
    history[index] = invalid
    called = []

    def forecast(_history: Sequence[float]) -> float:
        called.append(True)
        return 2.0

    with pytest.raises(ValueError, match=rf"demand\[{index}\] must be finite and non-negative"):
        backtest(history, "constant", forecast, holdout=2)
    assert not called  # validates all actuals before consulting the model


@pytest.mark.parametrize("invalid", [-1.0, -0.01, math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("index", [3, 4])
def test_backtest_rejects_invalid_custom_forecast_at_original_period(
    invalid: float, index: int
) -> None:
    def model(history: Sequence[float]) -> float:
        return invalid if len(history) == index else 2.0

    with pytest.raises(
        ValueError, match=rf"custom forecast\[{index}\] must be finite and non-negative"
    ):
        backtest([3.0, 4.0, 5.0, 6.0, 7.0], "custom", model, holdout=2)


def test_backtest_allows_zero_forecasts_and_demand() -> None:
    result = backtest([0.0, 0.0, 0.0, 0.0], "zero", lambda _history: 0.0, holdout=1)
    assert result.forecasts == (0.0,)
    assert result.mae == 0.0
    assert result.rmse == 0.0
    assert result.mase is None


def test_backtest_allows_finite_large_predictions() -> None:
    result = backtest([0.0, 0.0, 1e200], "large", lambda _history: 1e200, holdout=1)
    assert result.mae == 0.0
    assert result.mase is None


def test_backtest_existing_naive_metrics_unchanged() -> None:
    result = backtest([10.0, 12.0, 8.0, 10.0, 14.0, 6.0, 10.0, 14.0], "naive", naive, 2)
    assert result.forecasts == (6.0, 10.0)
    assert (result.mae, result.rmse, result.bias, result.mase) == (4.0, 4.0, -4.0, 1.0)
