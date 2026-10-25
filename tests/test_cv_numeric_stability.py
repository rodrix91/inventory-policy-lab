"""Regression: large, finite demand must not overflow coefficient-of-variation math."""

from __future__ import annotations

import math

import pytest

from inventory_policy_lab import coefficient_of_variation, demand_profile


def test_identical_large_demand_has_zero_variability() -> None:
    # statistics.fmean([1e308, 1e308]) raises OverflowError because the
    # intermediate sum is infinite, although the mean is representable.
    assert coefficient_of_variation([1e308, 1e308]) == 0.0
    assert demand_profile([1e308, 1e308]).cv2 == 0.0
    assert demand_profile([1e308, 1e308]).category == "smooth"


def test_large_finite_variability_keeps_its_true_ratio() -> None:
    # Scaling [1e308, 1e308, 0] to [1, 1, 0] gives CV = sqrt(1/2).
    cv = coefficient_of_variation([1e308, 1e308, 0])
    assert cv == pytest.approx(math.sqrt(0.5))


@pytest.mark.parametrize(
    ("series", "category"),
    [
        ([1e308, 1e306, 1e306], "erratic"),
        ([1e308, 0.0, 1e306, 0.0, 1e306], "lumpy"),
        ([1e308, 0.0, 1e308], "intermittent"),
    ],
)
def test_large_nonzero_sizes_preserve_demand_pattern_classification(
    series: list[float], category: str
) -> None:
    profile = demand_profile(series)
    assert profile.category == category
    assert profile.cv2 is not None
    assert math.isfinite(profile.cv2)


def test_existing_small_scale_and_zero_demand_behavior() -> None:
    assert coefficient_of_variation([5.0, 15.0]) == pytest.approx(0.5)
    assert coefficient_of_variation([0.0, 0.0]) is None
    assert demand_profile([0.0, 0.0]).category == "no demand"
