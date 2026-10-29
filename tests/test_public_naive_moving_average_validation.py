"""Direct naive and moving-average calls must reject malformed demand histories."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import pytest

from inventory_policy_lab import moving_average, naive


@pytest.mark.parametrize("forecast", [naive, moving_average])
def test_empty_demand_raises_actionable_error(
    forecast: Callable[[Sequence[float]], float],
) -> None:
    with pytest.raises(ValueError, match="needs at least one observed demand period"):
        forecast([])


@pytest.mark.parametrize("forecast", [naive, moving_average])
@pytest.mark.parametrize("index", [0, 1, 2])
@pytest.mark.parametrize("invalid", [-1.0, math.nan, math.inf, -math.inf])
def test_invalid_demand_is_rejected_at_original_position(
    forecast: Callable[[Sequence[float]], float], index: int, invalid: float
) -> None:
    demand = [2.0, 3.0, 4.0]
    demand[index] = invalid
    with pytest.raises(ValueError, match=rf"demand\[{index}\] must be finite and non-negative"):
        forecast(demand)


def test_moving_average_validates_earlier_periods_outside_its_window() -> None:
    with pytest.raises(ValueError, match=r"demand\[0\] must be finite and non-negative"):
        moving_average([-1.0, 2.0, 4.0], window=1)


def test_valid_zero_and_large_finite_demand_remain_supported() -> None:
    assert naive([0.0, 1e308]) == 1e308
    assert moving_average([0.0, 1e308, 1e308], window=2) == pytest.approx(1e308)
