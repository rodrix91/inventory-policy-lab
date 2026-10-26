"""Standalone XYZ classification must reject impossible numerical inputs."""

from __future__ import annotations

import math

import pytest

from inventory_policy_lab import coefficient_of_variation, xyz_class


@pytest.mark.parametrize(
    ("cv", "expected"),
    [
        (0.0, "X"),
        (0.5, "X"),
        (0.5001, "Y"),
        (1.0, "Y"),
        (1.0001, "Z"),
        (None, "Z"),
    ],
)
def test_valid_default_xyz_categories_unchanged(cv: float | None, expected: str) -> None:
    assert xyz_class(cv) == expected


def test_explicit_finite_xyz_cutoffs_and_real_demand_series() -> None:
    assert xyz_class(0.2, x=0.2, y=0.4) == "X"
    assert xyz_class(0.3, x=0.2, y=0.4) == "Y"
    assert xyz_class(0.5, x=0.2, y=0.4) == "Z"
    assert xyz_class(coefficient_of_variation([5, 15])) == "X"


@pytest.mark.parametrize("cv", [-1.0, -math.inf, math.inf, math.nan])
def test_nonfinite_or_negative_cv_is_not_silently_classified(cv: float) -> None:
    with pytest.raises(ValueError, match="coefficient of variation must be finite"):
        xyz_class(cv)


@pytest.mark.parametrize(
    ("x", "y"),
    [
        (0.0, 1.0),
        (-0.1, 1.0),
        (0.5, 0.5),
        (1.5, 1.0),
        (math.nan, 1.0),
        (0.5, math.nan),
        (math.inf, 1.0),
        (0.5, math.inf),
        (-math.inf, 1.0),
        (0.5, -math.inf),
    ],
)
def test_invalid_xyz_cutoffs_fail_even_for_no_demand(x: float, y: float) -> None:
    for cv in (0.3, None):
        with pytest.raises(ValueError, match="XYZ thresholds must satisfy"):
            xyz_class(cv, x=x, y=y)


def test_xyz_api_and_report_configuration_use_the_same_cutoff_rule() -> None:
    from inventory_policy_lab import Config, ConfigError

    Config(xyz_thresholds=(0.4, 0.8)).validate()
    assert xyz_class(0.7, x=0.4, y=0.8) == "Y"
    with pytest.raises(ConfigError, match="XYZ thresholds"):
        Config(xyz_thresholds=(0.8, 0.4)).validate()
    with pytest.raises(ValueError, match="XYZ thresholds"):
        xyz_class(0.7, x=0.8, y=0.4)
