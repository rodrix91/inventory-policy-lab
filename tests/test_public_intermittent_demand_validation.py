"""Croston and SBA reject impossible demand instead of concealing corrupted data."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import pytest

from inventory_policy_lab import croston, sba


@pytest.mark.parametrize("method", [croston, sba])
@pytest.mark.parametrize("invalid", [-1.0, -0.01, math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("position", [0, 2])
def test_direct_intermittent_forecast_rejects_invalid_demand(
    method: Callable[[Sequence[float]], float], invalid: float, position: int
) -> None:
    demand = [3.0, 0.0, 5.0]
    demand[position] = invalid
    with pytest.raises(ValueError, match=rf"demand\[{position}\] must be finite and non-negative"):
        method(demand)


@pytest.mark.parametrize("method", [croston, sba])
def test_zero_demand_and_finite_nonzero_demand_remain_supported(
    method: Callable[[Sequence[float]], float],
) -> None:
    assert method([]) == 0.0
    assert method([0.0, 0.0, 0.0]) == 0.0
    assert math.isfinite(method([0.0, 1e200, 0.0, 1e200]))
