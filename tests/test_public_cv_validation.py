"""The standalone CV API must reject invalid demand rather than return misleading statistics."""

from __future__ import annotations

import math

import pytest

from inventory_policy_lab import coefficient_of_variation


@pytest.mark.parametrize("invalid", [-1.0, -0.01, math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("position", [0, 2])
def test_public_cv_rejects_nonfinite_or_negative_demand(invalid: float, position: int) -> None:
    demand = [2.0, 0.0, 3.0]
    demand[position] = invalid
    with pytest.raises(ValueError, match=rf"demand\[{position}\] must be finite and non-negative"):
        coefficient_of_variation(demand)


def test_empty_and_zero_only_demand_have_no_defined_cv() -> None:
    assert coefficient_of_variation([]) is None
    assert coefficient_of_variation([0.0, 0.0]) is None


def test_regular_valid_demand_retains_existing_coefficient() -> None:
    assert coefficient_of_variation([5.0, 15.0]) == pytest.approx(0.5)
    assert coefficient_of_variation([10.0, 10.0, 10.0]) == 0.0


def test_large_finite_nonnegative_demand_retains_stable_result() -> None:
    assert coefficient_of_variation([1e308, 1e308]) == pytest.approx(0.0)
