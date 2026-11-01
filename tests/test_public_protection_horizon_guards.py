"""Public protection horizons reject malformed times and overflowing sums."""

from __future__ import annotations

import math
from typing import Any

import pytest

from inventory_policy_lab import (
    dynamic_levels,
    interval_demands,
    period_safety_stocks,
    protection_periods,
)

BAD_TIMES: tuple[Any, ...] = (
    -0.1,
    -1,
    True,
    False,
    math.nan,
    math.inf,
    -math.inf,
    "1",
    None,
    [],
    {},
    1 + 0j,
    object(),
    10**400,
)


@pytest.mark.parametrize("field", ("lead_time", "review_period"))
@pytest.mark.parametrize("invalid", BAD_TIMES)
def test_protection_periods_reject_malformed_times(field: str, invalid: Any) -> None:
    values: dict[str, Any] = {"lead_time": 1.0, "review_period": 1.0}
    values[field] = invalid
    with pytest.raises(ValueError, match=f"{field} must be finite and non-negative"):
        protection_periods(values["lead_time"], values["review_period"])


@pytest.mark.parametrize(
    ("lead", "review", "expected"),
    [
        (0.0, 0.0, 0),
        (0.2, 0.29, 0),
        (0.25, 0.25, 1),
        (0.7, 0.8, 2),
        (1.49, 0.0, 1),
        (1.5, 0.0, 2),
        (2.0, 0.49, 2),
    ],
)
def test_valid_horizons_preserve_half_up_rounding(
    lead: float, review: float, expected: int
) -> None:
    assert protection_periods(lead, review) == expected


def test_overflowing_sum_is_rejected_even_when_both_inputs_are_finite() -> None:
    assert math.isfinite(1e308)
    with pytest.raises(ValueError, match="protection period total must be finite"):
        protection_periods(1e308, 1e308)


def test_dynamic_apis_propagate_invalid_horizon_diagnostic() -> None:
    forecasts = [10.0, 20.0, 30.0, 40.0]
    for method in (
        lambda: interval_demands(forecasts, 2, -1.0, 0.0),
        lambda: dynamic_levels(forecasts, 2, 1.0, math.nan, 5.0),
        lambda: period_safety_stocks(forecasts, 2, 1e308, 1e308, 0.2),
    ):
        with pytest.raises(ValueError, match="must be finite"):
            method()


def test_zero_periods_still_validate_the_protection_horizon() -> None:
    with pytest.raises(ValueError, match="lead_time must be finite and non-negative"):
        interval_demands([], 0, -1.0, 0.0)


def test_valid_horizon_preserves_dynamic_levels_and_safety_stock() -> None:
    forecasts = [10.0, 20.0, 30.0, 40.0]
    assert interval_demands(forecasts, 2, 0.5, 0.5) == (20.0, 30.0)
    assert dynamic_levels(forecasts, 2, 0.5, 0.5, 5.0) == (25.0, 35.0)
    assert period_safety_stocks(forecasts, 2, 0.5, 0.5, 0.2) == (4.0, 6.0)
