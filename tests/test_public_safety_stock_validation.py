"""The public normal safety-stock API must match the validated CLI policy."""

from __future__ import annotations

import math
from typing import Any

import pytest

from inventory_policy_lab import build_policy, safety_stock


@pytest.mark.parametrize("level", [0.0, 0.49, 1.0, 1.01, math.nan, math.inf, -math.inf])
def test_invalid_normal_service_levels_are_rejected(level: float) -> None:
    with pytest.raises(ValueError, match="service_level must be at least 0.5 and below 1"):
        safety_stock(level, 100, 20, 2)


@pytest.mark.parametrize("invalid", [-1.0, math.nan, math.inf, -math.inf])
@pytest.mark.parametrize(
    "field",
    [
        "demand_per_period",
        "sigma_demand",
        "lead_time",
        "sigma_lead_time",
        "review_period",
    ],
)
def test_invalid_normal_policy_inputs_are_rejected(field: str, invalid: float) -> None:
    params = {
        "demand_per_period": 100.0,
        "sigma_demand": 20.0,
        "lead_time": 2.0,
        "sigma_lead_time": 0.5,
        "review_period": 1.0,
    }
    params[field] = invalid
    with pytest.raises(ValueError, match=f"{field} must be finite and non-negative"):
        safety_stock(
            0.95,
            params["demand_per_period"],
            params["sigma_demand"],
            params["lead_time"],
            params["sigma_lead_time"],
            params["review_period"],
        )


@pytest.mark.parametrize("invalid", [True, False, "20.0", None, 1 + 2j, object(), 10**400])
@pytest.mark.parametrize(
    "field",
    [
        "demand_per_period",
        "sigma_demand",
        "lead_time",
        "sigma_lead_time",
        "review_period",
    ],
)
def test_malformed_normal_policy_amounts_raise_clear_errors(
    field: str, invalid: Any
) -> None:
    values: dict[str, Any] = {
        "demand_per_period": 100.0,
        "sigma_demand": 20.0,
        "lead_time": 2.0,
        "sigma_lead_time": 0.5,
        "review_period": 1.0,
    }
    values[field] = invalid
    with pytest.raises(ValueError, match=f"{field} must be finite and non-negative"):
        safety_stock(
            0.95,
            values["demand_per_period"],
            values["sigma_demand"],
            values["lead_time"],
            values["sigma_lead_time"],
            values["review_period"],
        )


@pytest.mark.parametrize(
    "invalid",
    [True, False, "0.95", None, 1 + 2j, object(), 10**400],
)
def test_malformed_normal_service_levels_have_the_same_public_error(invalid: Any) -> None:
    with pytest.raises(ValueError, match="service_level must be at least 0.5 and below 1"):
        safety_stock(invalid, 100, 20, 2)


def test_zero_safety_stock_does_not_skip_malformed_parameter_validation() -> None:
    with pytest.raises(ValueError, match="sigma_demand must be finite and non-negative"):
        safety_stock(0.5, 100, True, 1)


def test_build_policy_rejects_invalid_normal_parameters_too() -> None:
    with pytest.raises(ValueError, match="service_level"):
        build_policy(0.4, 100, 20, 2)
    with pytest.raises(ValueError, match="sigma_demand"):
        build_policy(0.95, 100, -20, 2)


def test_half_service_level_avoids_zero_times_overflow() -> None:
    # Both inputs are finite even though their protection-period sum overflows.
    assert safety_stock(0.5, 1e308, 1e308, 1e308, 1e308, 1e308) == (0.0, 0.0)


def test_valid_nonnegative_inputs_keep_normal_quantile_formula() -> None:
    z, stock = safety_stock(0.95, 100, 20, 2, sigma_lead_time=0.5, review_period=1)
    expected = math.sqrt(3 * 20**2 + 100**2 * 0.5**2)
    assert stock == pytest.approx(z * expected)
    assert z > 0
    assert safety_stock(0.95, 0, 0, 0, 0, 0)[1] == 0.0
