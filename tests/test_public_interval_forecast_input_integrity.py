"""Public interval residuals reject bad demand, forecasts and arithmetic overflow."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, cast

import pytest

from inventory_policy_lab import interval_forecast_errors


def _last_period(history: Sequence[float], periods: int) -> float:
    return history[-1] * periods


def _unexpected_forecast(_history: Sequence[float], _periods: int) -> float:
    raise AssertionError("invalid demand must be rejected before forecasting")


@pytest.mark.parametrize(
    "invalid",
    [True, False, "3", None, 1 + 0j, object(), math.nan, math.inf, -math.inf, -1, 10**400],
)
@pytest.mark.parametrize("index", [0, 2])
def test_invalid_demand_is_rejected_at_original_index_before_forecast(
    invalid: Any, index: int
) -> None:
    history = [2.0, 3.0, 4.0]
    history[index] = cast(float, invalid)
    with pytest.raises(ValueError, match=rf"demand\[{index}\] must be finite and non-negative"):
        interval_forecast_errors(history, _unexpected_forecast, periods=1, start=1)


@pytest.mark.parametrize(
    "invalid",
    [True, False, "3",  1 + 0j, object(), math.nan, math.inf, -math.inf, 10**400],
)
def test_invalid_forecasts_are_rejected_with_rolling_origin(invalid: Any) -> None:
    def malformed(_history: Sequence[float], _periods: int) -> float:
        return cast(float, invalid)

    with pytest.raises(ValueError, match="forecast at origin 1 must be finite"):
        interval_forecast_errors([2.0, 3.0], malformed, periods=1, start=1)


def test_later_invalid_forecast_preserves_its_origin_index() -> None:
    def forecast(history: Sequence[float], _periods: int) -> float | None:
        return None if len(history) == 1 else math.nan

    with pytest.raises(ValueError, match="forecast at origin 2 must be finite"):
        interval_forecast_errors([2.0, 3.0, 4.0], forecast, periods=1, start=1)


def test_finite_inputs_with_unrepresentable_interval_total_are_rejected() -> None:
    with pytest.raises(ValueError, match="forecast error at origin 1 is not finite"):
        interval_forecast_errors([1.0, 1e308, 1e308], _last_period, periods=2, start=1)


def test_subtraction_and_relative_error_overflow_are_rejected() -> None:
    def negative(_history: Sequence[float], _periods: int) -> float:
        return -1e308

    with pytest.raises(ValueError, match="forecast error at origin 1 is not finite"):
        interval_forecast_errors([1.0, 1e308], negative, periods=1, start=1)

    def tiny(_history: Sequence[float], _periods: int) -> float:
        return 1e-308

    with pytest.raises(ValueError, match="forecast error at origin 1 is not finite"):
        interval_forecast_errors([1.0, 1e308], tiny, periods=1, start=1, relative=True)


def test_normal_forecast_errors_and_skipped_origins_remain_unchanged() -> None:
    history = [10.0, 12.0, 14.0, 16.0, 18.0]
    assert interval_forecast_errors(history, _last_period, 2, 2) == (6.0, 6.0)
    assert interval_forecast_errors(history, _last_period, 2, 2, relative=True) == (
        0.25, 6 / 28,
    )

    def no_model(_history: Sequence[float], _periods: int) -> float | None:
        return None

    assert interval_forecast_errors(history, no_model, 1, 1) == ()

    def negative(_history: Sequence[float], _periods: int) -> float:
        return -1.0

    assert interval_forecast_errors([1.0, 2.0], negative, 1, 1) == (3.0,)
    assert interval_forecast_errors([1.0, 2.0], negative, 1, 1, relative=True) == ()
    assert interval_forecast_errors([math.nan], _unexpected_forecast, 0, 1) == ()
