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

@pytest.mark.parametrize(
    ("series", "expected"),
    [
        ([0.0, 5e-324], 1.0),
        ([5e-324, 1e-323], 1.0 / 3.0),
        ([5e-324, 4e-323], 7.0 / 9.0),
        ([5e-324, 5e-324], 0.0),
    ],
)
def test_subnormal_demand_retains_real_variation(
    series: list[float], expected: float
) -> None:
    # The old unscaled mean and standard deviation could both underflow
    # even when observations were positive and genuinely different.
    assert coefficient_of_variation(series) == pytest.approx(expected)


def test_cv_is_scale_invariant_across_tiny_normal_and_huge_observations() -> None:
    reference = coefficient_of_variation([1.0, 8.0, 0.0])
    assert reference == pytest.approx(math.sqrt(114.0) / 9.0)
    for factor in (5e-324, 1e-300, 1.0, 1e300, 1e307):
        demand = [factor, 8 * factor, 0.0]
        assert demand[0] != demand[1]
        assert math.isfinite(demand[1])
        assert coefficient_of_variation(demand) == pytest.approx(reference)


def test_subnormal_history_is_classified_by_observed_variation() -> None:
    # 1:8 positive-size ratio has CV^2=(7/9)^2 > 0.49, so it is erratic
    # with demand every period and lumpy with intervening zero periods.
    erratic = demand_profile([5e-324, 4e-323])
    lumpy = demand_profile([5e-324, 0.0, 4e-323, 0.0])
    assert erratic.category == "erratic"
    assert lumpy.category == "lumpy"
    assert erratic.cv2 == pytest.approx((7 / 9) ** 2)
    assert lumpy.cv2 == pytest.approx(erratic.cv2)
    assert demand_profile([0.0, 0.0]).category == "no demand"
