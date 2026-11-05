"""Dynamic stock policies reject invalid forecast histories and keep finite means."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import pytest

from inventory_policy_lab import dynamic_levels, interval_demands, period_safety_stocks


def interval(values: list[float], periods: int) -> tuple[float, ...]:
    return interval_demands(values, periods, 1.0, 0.0)


def levels(values: list[float], periods: int) -> tuple[float, ...]:
    return dynamic_levels(values, periods, 1.0, 0.0, 5.0)


def stocks(values: list[float], periods: int) -> tuple[float, ...]:
    return period_safety_stocks(values, periods, 1.0, 0.0, 0.2)


APIS: tuple[Callable[[list[float], int], tuple[float, ...]], ...] = (
    interval,
    levels,
    stocks,
)


@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("index", [0, 1, 3])
@pytest.mark.parametrize(
    "invalid",
    [math.nan, math.inf, -math.inf, -1.0, True, False, "12", None, 1 + 0j, 10**400],
)
def test_dynamic_forecasts_reject_invalid_values_at_original_index(
    api: Callable[[list[float], int], tuple[float, ...]], index: int, invalid: Any
) -> None:
    values = [10.0, 20.0, 30.0, 40.0]
    values[index] = invalid
    with pytest.raises(ValueError, match=rf"forecasts\[{index}\] must be finite and non-negative"):
        api(values, 2)


@pytest.mark.parametrize("api", APIS)
def test_invalid_forecasts_are_rejected_even_with_zero_output_periods(
    api: Callable[[list[float], int], tuple[float, ...]]
) -> None:
    # Reject a corrupted input even if an empty output was requested.
    with pytest.raises(ValueError, match=r"forecasts\[0\] must be finite and non-negative"):
        api([math.nan], 0)


def test_large_finite_interval_mean_does_not_overflow() -> None:
    # Each observed forecast fits in float. Their ordinary fsum overflows
    # even though the average demand per period is also finite.
    assert interval_demands([0.0, 1e308, 1e308], 1, 2.0, 0.0) == (1e308,)
    assert interval_demands([0.0, 1e308, 1e308, 0.0], 2, 2.0, 0.0) == (
        1e308,
        5e307,
    )


def test_ordinary_dynamic_policy_calculations_and_input_remain_unchanged() -> None:
    values = [10.0, 20.0, 30.0, 40.0]
    unchanged = values[:]
    assert interval(values, 2) == (20.0, 30.0)
    assert levels(values, 2) == (25.0, 35.0)
    assert stocks(values, 2) == pytest.approx((4.0, 6.0))
    assert interval([10.0], 0) == ()
    assert values == unchanged
