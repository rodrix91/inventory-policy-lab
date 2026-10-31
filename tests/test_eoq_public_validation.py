"""Public EOQ calculations reject invalid demand/cost inputs before producing a policy."""

from __future__ import annotations

import math
from typing import Any

import pytest

from inventory_policy_lab import eoq


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf, -1.0])
@pytest.mark.parametrize("parameter", ["annual_demand", "ordering_cost", "holding_cost"])
def test_eoq_rejects_nonfinite_or_negative_inputs(parameter: str, invalid: float) -> None:
    values = {"annual_demand": 1200.0, "ordering_cost": 30.0, "holding_cost": 0.5}
    values[parameter] = invalid
    label = {
        "annual_demand": "annual demand",
        "ordering_cost": "ordering cost",
        "holding_cost": "holding cost",
    }[parameter]
    with pytest.raises(ValueError, match=f"{label} must be finite and non-negative"):
        eoq(values["annual_demand"], values["ordering_cost"], values["holding_cost"])


@pytest.mark.parametrize("invalid", [True, False, "30.0", None, 1 + 2j, object(), 10**400])
@pytest.mark.parametrize("parameter", ["annual_demand", "ordering_cost", "holding_cost"])
def test_malformed_public_eoq_inputs_have_actionable_errors(
    parameter: str, invalid: Any
) -> None:
    values: dict[str, Any] = {
        "annual_demand": 1200.0,
        "ordering_cost": 30.0,
        "holding_cost": 0.5,
    }
    values[parameter] = invalid
    labels = {
        "annual_demand": "annual demand",
        "ordering_cost": "ordering cost",
        "holding_cost": "holding cost",
    }
    with pytest.raises(ValueError, match=f"{labels[parameter]} must be finite and non-negative"):
        eoq(values["annual_demand"], values["ordering_cost"], values["holding_cost"])


def test_zero_demand_cannot_hide_boolean_ordering_cost() -> None:
    with pytest.raises(ValueError, match="ordering cost must be finite and non-negative"):
        eoq(0, True, 1.0)


@pytest.mark.parametrize(
    ("annual_demand", "ordering_cost", "holding_cost", "message"),
    [
        (0.0, math.nan, 1.0, "ordering cost"),
        (0.0, 1.0, math.inf, "holding cost"),
        (10.0, math.nan, 0.0, "ordering cost"),
        (math.nan, 0.0, 0.0, "annual demand"),
    ],
)
def test_undefined_quantities_must_not_hide_invalid_other_inputs(
    annual_demand: float, ordering_cost: float, holding_cost: float, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        eoq(annual_demand, ordering_cost, holding_cost)


def test_standalone_eoq_retains_all_valid_boundary_and_extreme_behavior() -> None:
    assert eoq(1200, 30, 0.5) == pytest.approx(math.sqrt(144_000))
    assert eoq(0, 30, 0.5) is None
    assert eoq(1200, 30, 0) is None
    assert eoq(1200, 0, 0.5) == 0.0
    assert eoq(0, 0, 0) is None

    # Preserve the existing log-domain correction of intermediate overflow.
    assert eoq(1e308, 1e308, 1e308) == pytest.approx(math.sqrt(2) * 1e154)
    # A mathematically unrepresentable final quantity still returns +infinity.
    assert eoq(1e308, 1e308, 1e-308) == math.inf
