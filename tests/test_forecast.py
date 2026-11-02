"""Forecasting methods, the backtest and the selection rule."""

from __future__ import annotations

from collections.abc import Callable, Sequence

import pytest

from inventory_policy_lab import backtest, croston, moving_average, naive, sba, ses
from inventory_policy_lab.forecast import BacktestResult, naive_scale, pick_best


def test_naive_and_moving_average() -> None:
    assert naive([1, 2, 7]) == 7
    assert moving_average([1, 2, 3, 4]) == 3
    assert moving_average([1, 2, 3, 4], window=2) == 3.5
    assert moving_average([4], window=3) == 4  # shorter history: mean of what exists


@pytest.mark.parametrize("method", [naive, moving_average, ses, croston, sba])
def test_forecast_methods_reject_empty_histories(method: Callable[[Sequence[float]], float]) -> None:
    # Empty history means no observations, not a measured zero-demand period.
    with pytest.raises(ValueError, match="needs at least one observed demand period"):
        method([])


@pytest.mark.parametrize("method", [croston, sba])
def test_intermittent_methods_preserve_observed_zero_demand(
    method: Callable[[Sequence[float]], float],
) -> None:
    assert method([0.0]) == 0.0
    assert method([0.0, 0.0, 0.0]) == 0.0


def test_ses_by_hand() -> None:
    # level 10 -> 10 + 0.5 * (20 - 10) = 15 -> 15 + 0.5 * (0 - 15) = 7.5
    assert ses([10, 20, 0], alpha=0.5) == pytest.approx(7.5)
    assert ses([3]) == 3


def test_croston_and_sba_by_hand() -> None:
    history = [0, 0, 6, 0, 0, 0, 9, 0]
    # first demand at period 3: size 6, interval 3
    # next demand 4 periods later: size 6 + 0.1 * (9 - 6) = 6.3, interval 3 + 0.1 * (4 - 3) = 3.1
    assert croston(history) == pytest.approx(6.3 / 3.1)
    assert sba(history) == pytest.approx(0.95 * 6.3 / 3.1)
    assert croston([0, 0]) == 0
    assert sba([0, 0]) == 0
    assert croston([4]) == 4


def test_naive_scale() -> None:
    assert naive_scale([10, 12, 8, 10, 14, 6]) == 4  # (2 + 4 + 2 + 4 + 8) / 5


def test_backtest_by_hand() -> None:
    series = [10, 12, 8, 10, 14, 6, 10, 14]
    result = backtest(series, "naive", naive, holdout=2)
    # forecasts 6 and 10 for actuals 10 and 14: errors -4, -4
    assert result.forecasts == (6, 10)
    assert result.mae == 4
    assert result.rmse == 4
    assert result.bias == -4
    assert result.mase == 1  # MAE 4 / naive scale 4


def test_backtest_mase_undefined_on_constant_training() -> None:
    result = backtest([5, 5, 5, 7], "naive", naive, holdout=1)
    assert result.mae == 2
    assert result.mase is None


@pytest.mark.parametrize(("series", "holdout"), [([1, 2, 3], 0), ([1, 2, 3], 2)])
def test_backtest_needs_training_data(series: list[float], holdout: int) -> None:
    with pytest.raises(ValueError, match="at least 2 training periods"):
        backtest(series, "naive", naive, holdout)


def _result(name: str, mae: float, mase: float | None) -> BacktestResult:
    return BacktestResult(method=name, forecasts=(), mae=mae, rmse=mae, bias=0.0, mase=mase)


def test_pick_best_by_mase_then_mae_and_first_on_ties() -> None:
    assert pick_best([_result("a", 3, 0.9), _result("b", 4, 0.8)]).method == "b"
    assert pick_best([_result("a", 3, 0.8), _result("b", 3, 0.8)]).method == "a"
    assert pick_best([_result("a", 3, None), _result("b", 2, None)]).method == "b"
