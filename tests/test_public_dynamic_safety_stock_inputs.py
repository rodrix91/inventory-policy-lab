"""Dynamic stock levels reject invalid safety stock without changing valid formulas."""

from __future__ import annotations

import math
from typing import Any

import pytest

from inventory_policy_lab import dynamic_levels, period_safety_stocks

FORECASTS = [10.0, 20.0, 30.0, 40.0]

INVALID_SCALARS: tuple[Any, ...] = (
    -1,
    -0.1,
    math.nan,
    math.inf,
    -math.inf,
    True,
    False,
    "5",
    b"5",
    None,
    {},
    1 + 2j,
    object(),
    10**400,
)


@pytest.mark.parametrize("invalid", INVALID_SCALARS)
def test_bad_scalar_safety_stock_fails_before_generating_levels(invalid: Any) -> None:
    with pytest.raises(ValueError, match="safety_stock must be finite and non-negative"):
        dynamic_levels(FORECASTS, 2, 1.0, 0.0, invalid)


@pytest.mark.parametrize(
    "invalid",
    [
        (-1.0, 1.0),
        (1.0, -0.1),
        (math.nan, 1.0),
        (1.0, math.inf),
        (-math.inf, 1.0),
        (True, 1.0),
        (1.0, False),
        ("1.0", 1.0),
        (1.0, None),
        (object(), 1.0),
        (10**400, 1.0),
    ],
)
def test_bad_per_period_stock_fails_without_partial_result(invalid: Any) -> None:
    with pytest.raises(ValueError, match="safety_stock entries must be finite and non-negative"):
        dynamic_levels(FORECASTS, 2, 1.0, 0.0, invalid)


def test_sequence_length_error_is_unchanged() -> None:
    with pytest.raises(ValueError, match="safety_stock needs one value per period"):
        dynamic_levels(FORECASTS, 2, 1.0, 0.0, (2.0,))


def test_valid_scalar_and_sequence_stock_preserve_existing_levels() -> None:
    assert dynamic_levels(FORECASTS, 2, 1.0, 0.0, 5.0) == (25.0, 35.0)
    assert dynamic_levels(FORECASTS, 2, 1.0, 0.0, 0.0) == (20.0, 30.0)
    assert dynamic_levels(FORECASTS, 2, 1.0, 0.0, (5.0, 7.0)) == (25.0, 37.0)
    assert dynamic_levels(FORECASTS, 2, 1.0, 0.0, [0.0, 5.0]) == (20.0, 35.0)
    assert dynamic_levels(FORECASTS, 0, 1.0, 0.0, ()) == ()
    assert dynamic_levels(FORECASTS, 0, 1.0, 0.0, 0.0) == ()


def test_zero_periods_still_reject_invalid_stock() -> None:
    with pytest.raises(ValueError, match="safety_stock must be finite and non-negative"):
        dynamic_levels(FORECASTS, 0, 1.0, 0.0, math.nan)


@pytest.mark.parametrize("invalid", INVALID_SCALARS[2:] + (1 + 0j,))
def test_period_safety_stocks_rejects_nonfinite_or_nonnumeric_error_quantiles(invalid: Any) -> None:
    # A malformed quantile used to create NaN/inf stock levels, or crash with
    # TypeError. Booleans were also interpreted as 0 or 1.
    with pytest.raises(ValueError, match="relative_error must be a finite number"):
        period_safety_stocks(FORECASTS, 2, 1.0, 0.0, invalid)


def test_period_safety_stocks_validates_error_even_when_no_periods_are_requested() -> None:
    with pytest.raises(ValueError, match="relative_error must be a finite number"):
        period_safety_stocks(FORECASTS, 0, 1.0, 0.0, math.nan)
    assert period_safety_stocks(FORECASTS, 0, 1.0, 0.0, 0.2) == ()


def test_period_safety_stocks_keeps_valid_positive_and_negative_quantiles() -> None:
    assert period_safety_stocks(FORECASTS, 2, 1.0, 0.0, 0.2) == pytest.approx((4.0, 6.0))
    assert period_safety_stocks(FORECASTS, 2, 1.0, 0.0, -0.5) == (0.0, 0.0)
    assert period_safety_stocks(FORECASTS, 2, 1.0, 0.0, 0) == (0.0, 0.0)
