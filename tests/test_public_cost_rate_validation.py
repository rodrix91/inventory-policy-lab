"""Public cost rates must reject malformed money inputs before scoring replays."""

from __future__ import annotations

import math
from typing import Any

import pytest

from inventory_policy_lab import CostRates, replay_cost, simulate


def make_rates(name: str, value: Any) -> CostRates:
    """Exercise each direct API field with the same invalid inputs."""
    return CostRates(
        order=value if name == "order" else 0.0,
        holding=value if name == "holding" else 0.0,
        stockout=value if name == "stockout" else 0.0,
    )


@pytest.mark.parametrize("name", ["order", "holding", "stockout"])
@pytest.mark.parametrize(
    "invalid",
    [
        True,
        False,
        "5.0",
        None,
        1 + 2j,
        object(),
        10**400,
        -1.0,
        math.nan,
        math.inf,
        -math.inf,
    ],
)
def test_invalid_public_cost_rate_has_actionable_value_error(name: str, invalid: Any) -> None:
    with pytest.raises(ValueError, match=f"{name} cost must be a finite number of at least 0"):
        make_rates(name, invalid)


def test_valid_zero_integer_and_fractional_rates_keep_replay_costs() -> None:
    rates = CostRates(order=10, holding=0.5, stockout=3)
    result = simulate([4, 4, 6, 4], 4, 8, lead_time=1)
    costs = replay_cost(result, rates)
    assert rates == CostRates(order=10.0, holding=0.5, stockout=3.0)
    assert (costs.orders, costs.unit_periods, costs.units_short) == (2, 14, 2)
    assert (costs.ordering, costs.holding, costs.stockout, costs.total) == (20, 7, 6, 33)
    assert CostRates() == CostRates(order=0, holding=0, stockout=0)


def test_malformed_cost_fails_before_any_replay_is_required() -> None:
    with pytest.raises(ValueError, match="stockout cost must be a finite number of at least 0"):
        CostRates(stockout=True)
