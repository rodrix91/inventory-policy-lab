"""Public dynamic forecasting APIs must reject malformed period counts."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import pytest

from inventory_policy_lab import dynamic_levels, interval_demands, period_safety_stocks

FORECASTS = [10.0, 20.0, 30.0, 40.0]


def demand(periods: Any) -> tuple[float, ...]:
    return interval_demands(FORECASTS, periods, lead_time=1.0, review_period=0.0)


def levels(periods: Any) -> tuple[float, ...]:
    return dynamic_levels(FORECASTS, periods, lead_time=1.0, review_period=0.0, safety_stock=5.0)


def stocks(periods: Any) -> tuple[float, ...]:
    return period_safety_stocks(
        FORECASTS, periods, lead_time=1.0, review_period=0.0, relative_error=0.2
    )


APIS: tuple[Callable[[Any], tuple[float, ...]], ...] = (demand, levels, stocks)
MALFORMED_COUNTS: tuple[Any, ...] = (
    True,
    False,
    1.0,
    1.5,
    "2",
    None,
    math.nan,
    math.inf,
    -math.inf,
    [],
    {},
    1 + 0j,
    object(),
)


@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("invalid", MALFORMED_COUNTS)
def test_public_dynamic_apis_reject_noninteger_counts(
    api: Callable[[Any], tuple[float, ...]], invalid: Any
) -> None:
    with pytest.raises(ValueError, match="periods must be a non-negative integer"):
        api(invalid)


@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("invalid", [-1, -3])
def test_public_dynamic_apis_reject_negative_counts(
    api: Callable[[Any], tuple[float, ...]], invalid: int
) -> None:
    with pytest.raises(ValueError, match="periods must be non-negative"):
        api(invalid)


def test_dynamic_levels_reject_bad_counts_before_processing_safety_stock() -> None:
    for count in (False, 1.5, -1):
        with pytest.raises(ValueError, match="periods must be"):
            dynamic_levels(
                FORECASTS, count, lead_time=1.0, review_period=0.0, safety_stock=(1.0, 2.0)
            )


def test_valid_zero_and_positive_counts_preserve_existing_formulas() -> None:
    for api in APIS:
        assert api(0) == ()
    assert demand(2) == (20.0, 30.0)
    assert levels(2) == (25.0, 35.0)
    assert stocks(2) == (4.0, 6.0)
    assert dynamic_levels(
        FORECASTS, 2, lead_time=1.0, review_period=0.0, safety_stock=(2.0, 3.0)
    ) == (22.0, 33.0)


def test_valid_count_preserves_forecast_coverage_diagnostic() -> None:
    with pytest.raises(ValueError, match="forecasts must cover 4 periods plus 1 ahead"):
        interval_demands(FORECASTS, 4, lead_time=1.0, review_period=0.0)
