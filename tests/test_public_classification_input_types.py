"""Public classification APIs must reject nonnumeric and boolean values cleanly."""

from __future__ import annotations

import math
from typing import Any

import pytest

import inventory_policy_lab as inventory


INVALID_NUMBERS: list[Any] = [
    True,
    False,
    "0.5",
    None,
    1 + 0j,
    object(),
    10**400,
    math.inf,
    -math.inf,
    math.nan,
]


@pytest.mark.parametrize("invalid", INVALID_NUMBERS)
@pytest.mark.parametrize("which", ["a", "b"])
def test_abc_rejects_malformed_thresholds_as_value_error(invalid: Any, which: str) -> None:
    settings = {"a": 0.5, "b": 0.95}
    settings[which] = invalid
    with pytest.raises(ValueError, match="ABC thresholds must satisfy"):
        inventory.abc_classes({"primary": 3.0, "secondary": 1.0}, a=settings["a"], b=settings["b"])


@pytest.mark.parametrize("invalid", [*INVALID_NUMBERS, -0.1])
def test_abc_rejects_malformed_sku_values_before_scoring(invalid: Any) -> None:
    with pytest.raises(ValueError, match="ABC item values must be finite and non-negative"):
        inventory.abc_classes({"valid": 3.0, "corrupt": invalid})


@pytest.mark.parametrize("invalid", INVALID_NUMBERS)
@pytest.mark.parametrize("which", ["x", "y"])
def test_xyz_rejects_malformed_thresholds_as_value_error(invalid: Any, which: str) -> None:
    settings = {"x": 0.5, "y": 1.0}
    settings[which] = invalid
    with pytest.raises(ValueError, match="XYZ thresholds must satisfy"):
        inventory.xyz_class(0.5, x=settings["x"], y=settings["y"])


# None is a documented, valid XYZ sentinel: an undefined CV maps to class Z.
@pytest.mark.parametrize("invalid", [*(v for v in INVALID_NUMBERS if v is not None), -0.1])
def test_xyz_rejects_malformed_cv_as_value_error(invalid: Any) -> None:
    with pytest.raises(ValueError, match="XYZ coefficient of variation must be finite"):
        inventory.xyz_class(invalid)


@pytest.mark.parametrize("invalid", INVALID_NUMBERS)
@pytest.mark.parametrize("which", ["adi_cutoff", "cv2_cutoff"])
def test_profile_rejects_malformed_cutoffs_even_without_demand(invalid: Any, which: str) -> None:
    settings = {"adi_cutoff": 1.32, "cv2_cutoff": 0.49}
    settings[which] = invalid
    with pytest.raises(ValueError, match="demand profile cutoffs must have finite"):
        inventory.demand_profile([], adi_cutoff=settings["adi_cutoff"], cv2_cutoff=settings["cv2_cutoff"])


@pytest.mark.parametrize("invalid", [*INVALID_NUMBERS, -0.1])
@pytest.mark.parametrize("method", [coefficient_of_variation, demand_profile])
def test_classifiers_report_corrupted_demand_index(method: Any, invalid: Any) -> None:
    with pytest.raises(ValueError, match=r"demand\[1\] must be finite and non-negative"):
        method([2.0, invalid, 4.0])


def test_valid_integer_float_zero_and_empty_inputs_preserve_results() -> None:
    assert inventory.abc_classes({"large": 3, "small": 1.0}, a=0.8, b=1.0) == {
        "large": "A",
        "small": "A",
    }
    assert inventory.abc_classes({"zero": 0.0}) == {"zero": "C"}
    assert inventory.abc_classes({}) == {}
    assert inventory.xyz_class(0.5, x=0.5, y=1.0) == "X"
    assert inventory.xyz_class(None) == "Z"
    assert inventory.coefficient_of_variation([0, 0.0]) is None
    assert inventory.demand_profile([0.0, 0.0]).category == "no demand"
    assert inventory.demand_profile([2.0, 0.0], adi_cutoff=2, cv2_cutoff=0).adi == 2.0
