"""Public rolling-origin error calculations reject malformed period and start inputs."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import pytest

from inventory_policy_lab import interval_forecast_errors


def _naive_total(history: Sequence[float], periods: int) -> float:
    return history[-1] * periods


def _unexpected_forecast(_history: Sequence[float], _periods: int) -> float:
    raise AssertionError("invalid interval settings must fail before fitting forecasts")


INVALID_TYPES: tuple[Any, ...] = (
    True,
    False,
    1.0,
    1.5,
    "2",
    None,
    math.nan,
    math.inf,
    -math.inf,
    [],
    {},
    1 + 0j,
    object(),
)


@pytest.mark.parametrize("invalid", INVALID_TYPES)
def test_start_must_be_a_real_integer_index(invalid: Any) -> None:
    with pytest.raises(ValueError, match="start must be an integer observation index"):
        interval_forecast_errors([10.0, 12.0, 14.0], _unexpected_forecast, 1, invalid)


@pytest.mark.parametrize("invalid", INVALID_TYPES)
def test_period_count_must_be_a_real_integer(invalid: Any) -> None:
    with pytest.raises(ValueError, match="periods must be a non-negative integer"):
        interval_forecast_errors([10.0, 12.0, 14.0], _unexpected_forecast, invalid, 1)


@pytest.mark.parametrize("invalid", [0, -1, -3])
def test_out_of_range_start_keeps_original_diagnostic(invalid: int) -> None:
    with pytest.raises(ValueError, match="start must be at least 1"):
        interval_forecast_errors([10.0, 12.0, 14.0], _unexpected_forecast, 1, invalid)


@pytest.mark.parametrize("invalid", [-1, -3])
def test_negative_integer_periods_do_not_silently_skip_residuals(invalid: int) -> None:
    with pytest.raises(ValueError, match="periods must be non-negative"):
        interval_forecast_errors([10.0, 12.0, 14.0], _unexpected_forecast, invalid, 1)


def test_valid_periods_zero_and_rolling_origins_are_unchanged() -> None:
    history = [10.0, 12.0, 14.0, 16.0, 18.0]
    assert interval_forecast_errors(history, _unexpected_forecast, 0, 2) == ()
    assert interval_forecast_errors(history, _naive_total, 2, 2) == (6.0, 6.0)
    assert interval_forecast_errors(history, _naive_total, 2, 1) == (6.0, 6.0, 6.0)
    assert interval_forecast_errors(history, _naive_total, 2, 2, relative=True) == (
        0.25,
        6 / 28,
    )
