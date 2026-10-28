"""The public demand-pattern classifier must not silently accept impossible inputs."""

from __future__ import annotations

import math

import pytest

from inventory_policy_lab import demand_profile


@pytest.mark.parametrize("invalid", [-1.0, -0.01, math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("position", [0, 2])
def test_invalid_demand_is_rejected_before_pattern_classification(
    invalid: float, position: int
) -> None:
    demand = [2.0, 0.0, 3.0]
    demand[position] = invalid
    with pytest.raises(ValueError, match=rf"demand\\[{position}\\] must be finite and non-negative"):
        demand_profile(demand)


@pytest.mark.parametrize(
    ("adi_cutoff", "cv2_cutoff"),
    [
        (0.0, 0.49),
        (-1.0, 0.49),
        (math.nan, 0.49),
        (math.inf, 0.49),
        (1.32, -0.1),
        (1.32, math.nan),
        (1.32, math.inf),
        (1.32, -math.inf),
    ],
)
def test_invalid_cutoffs_fail_even_for_empty_or_zero_demand(
    adi_cutoff: float, cv2_cutoff: float
) -> None:
    for demand in ([], [0.0, 0.0], [1.0, 0.0]):
        with pytest.raises(ValueError, match="demand profile cutoffs must have finite"):
            demand_profile(demand, adi_cutoff=adi_cutoff, cv2_cutoff=cv2_cutoff)


def test_valid_custom_cutoffs_and_normal_series_keep_original_categories() -> None:
    assert demand_profile([10.0, 11.0, 9.0]).category == "smooth"
    assert demand_profile([1.0, 0.0, 0.0, 40.0, 0.0, 2.0]).category == "lumpy"
    assert demand_profile([0.0, 0.0], cv2_cutoff=0.0).category == "no demand"
    profile = demand_profile([1.0, 1.0, 0.0], adi_cutoff=1.5, cv2_cutoff=0.49)
    assert profile.category == "intermittent"
    assert profile.nonzero_periods == 2
