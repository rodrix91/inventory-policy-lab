"""ABC, XYZ and Syntetos-Boylan classification."""

from __future__ import annotations

import pytest

from inventory_policy_lab import abc_classes, coefficient_of_variation, demand_profile, xyz_class


def test_abc_uses_the_cumulative_share_before_each_item() -> None:
    values = {"a": 70.0, "b": 15.0, "c": 10.0, "d": 5.0}
    # shares before: a 0%, b 70%, c 85%, d 95%
    assert abc_classes(values) == {"a": "A", "b": "A", "c": "B", "d": "C"}


def test_abc_ties_and_thresholds() -> None:
    classes = abc_classes({"z": 1.0, "big": 98.0, "y": 1.0}, a=0.5, b=0.99)
    # big alone is 98% of the total and still A; y (sorted before z) has 98% before it
    assert classes == {"big": "A", "y": "B", "z": "C"}


def test_abc_with_zero_total_is_all_c() -> None:
    assert abc_classes({"a": 0.0, "b": 0.0}) == {"a": "C", "b": "C"}


def test_cv_and_xyz() -> None:
    assert coefficient_of_variation([10, 10, 10]) == 0
    assert coefficient_of_variation([0, 0]) is None
    assert coefficient_of_variation([5, 15]) == pytest.approx(0.5)
    assert xyz_class(0.5) == "X"
    assert xyz_class(0.51) == "Y"
    assert xyz_class(1.0) == "Y"
    assert xyz_class(1.01) == "Z"
    assert xyz_class(None) == "Z"
    assert xyz_class(0.3, x=0.2, y=0.4) == "Y"


@pytest.mark.parametrize(
    ("demand", "category"),
    [
        ([10, 11, 9, 10], "smooth"),  # ADI 1, CV2 small
        ([1, 30, 2, 40], "erratic"),  # ADI 1, CV2 large
        ([5, 0, 0, 5, 0, 6], "intermittent"),  # ADI 2
        ([1, 0, 0, 40, 0, 2], "lumpy"),  # ADI 2, CV2 large
        ([0, 0, 0], "no demand"),
    ],
)
def test_syntetos_boylan_categories(demand: list[float], category: str) -> None:
    assert demand_profile(demand).category == category


def test_profile_values_at_the_cutoffs() -> None:
    profile = demand_profile([4, 0, 0, 8])
    assert profile.adi == 2.0
    assert profile.nonzero_periods == 2
    # sizes 4 and 8: mean 6, population sd 2, CV2 = (2/6)^2
    assert profile.cv2 == pytest.approx(1 / 9)
    # ADI exactly at the cut-off counts as intermittent (ADI >= 1.32)
    assert demand_profile([1, 1, 0], adi_cutoff=1.5).category == "intermittent"
    assert demand_profile([0, 0]).adi is None


# The invalid-value fixtures intentionally violate the float-typed public API.
# Parameter annotations describe the API contract, not the malformed runtime data.
INVALID_CLASSIFICATION_NUMBERS = [
    True,
    False,
    "0.5",
    None,
    1 + 0j,
    object(),
    10**400,
    float("inf"),
    float("-inf"),
    float("nan"),
]


@pytest.mark.parametrize("invalid", INVALID_CLASSIFICATION_NUMBERS)
@pytest.mark.parametrize("which", ["a", "b"])
def test_classifier_abc_rejects_malformed_thresholds(invalid: float, which: str) -> None:
    settings = {"a": 0.5, "b": 0.95}
    settings[which] = invalid
    with pytest.raises(ValueError, match="ABC thresholds must satisfy"):
        abc_classes({"primary": 3.0, "secondary": 1.0}, a=settings["a"], b=settings["b"])


@pytest.mark.parametrize("invalid", [*INVALID_CLASSIFICATION_NUMBERS, -0.1])
def test_classifier_abc_rejects_malformed_values(invalid: float) -> None:
    with pytest.raises(ValueError, match="ABC item values must be finite and non-negative"):
        abc_classes({"valid": 3.0, "corrupt": invalid})


@pytest.mark.parametrize("invalid", INVALID_CLASSIFICATION_NUMBERS)
@pytest.mark.parametrize("which", ["x", "y"])
def test_classifier_xyz_rejects_malformed_thresholds(invalid: float, which: str) -> None:
    settings = {"x": 0.5, "y": 1.0}
    settings[which] = invalid
    with pytest.raises(ValueError, match="XYZ thresholds must satisfy"):
        xyz_class(0.5, x=settings["x"], y=settings["y"])


# None is a documented valid sentinel for an undefined CV (class Z).
@pytest.mark.parametrize(
    "invalid",
    [*(v for v in INVALID_CLASSIFICATION_NUMBERS if v is not None), -0.1],
)
def test_classifier_xyz_rejects_malformed_cv(invalid: float) -> None:
    with pytest.raises(ValueError, match="XYZ coefficient of variation must be finite"):
        xyz_class(invalid)


@pytest.mark.parametrize("invalid", INVALID_CLASSIFICATION_NUMBERS)
@pytest.mark.parametrize("which", ["adi_cutoff", "cv2_cutoff"])
def test_classifier_profile_rejects_malformed_cutoffs(invalid: float, which: str) -> None:
    settings = {"adi_cutoff": 1.32, "cv2_cutoff": 0.49}
    settings[which] = invalid
    with pytest.raises(ValueError, match="demand profile cutoffs must have finite"):
        demand_profile(
            [],
            adi_cutoff=settings["adi_cutoff"],
            cv2_cutoff=settings["cv2_cutoff"],
        )


@pytest.mark.parametrize("invalid", [*INVALID_CLASSIFICATION_NUMBERS, -0.1])
def test_classifier_cv_and_profile_report_corrupt_observation_index(invalid: float) -> None:
    for method in (coefficient_of_variation, demand_profile):
        with pytest.raises(ValueError, match=r"demand\[1\] must be finite and non-negative"):
            method([2.0, invalid, 4.0])


def test_classifier_valid_numeric_values_and_zero_histories_are_unchanged() -> None:
    assert abc_classes({"large": 3.0, "small": 1.0}, a=0.8, b=1.0) == {
        "large": "A",
        "small": "A",
    }
    assert abc_classes({"zero": 0.0}) == {"zero": "C"}
    assert abc_classes({}) == {}
    assert xyz_class(0.5, x=0.5, y=1.0) == "X"
    assert xyz_class(None) == "Z"
    assert coefficient_of_variation([0.0, 0.0]) is None
    assert demand_profile([0.0, 0.0]).category == "no demand"
    assert demand_profile([2.0, 0.0], adi_cutoff=2.0, cv2_cutoff=0.0).adi == 2.0
