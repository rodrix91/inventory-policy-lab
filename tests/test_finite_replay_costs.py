"""Extreme but finite rates must not produce infinite monetary reports."""

from __future__ import annotations

import math

import pytest

from inventory_policy_lab import (
    CostBreakdown,
    CostRates,
    DataError,
    SimulationResult,
    replay_cost,
    simulate,
    total_cost,
)


@pytest.mark.parametrize(
    "rates",
    [
        CostRates(order=1e308),
        CostRates(holding=1e308),
        CostRates(stockout=1e308),
        CostRates(order=1e308 / 2, holding=1e308 / 14),
    ],
)
def test_finite_rate_multiplication_or_total_overflow_is_rejected(rates: CostRates) -> None:
    result = simulate([4, 4, 6, 4], 4, 8, lead_time=1)
    assert (result.orders_placed, result.average_on_hand, result.periods) == (2, 3.5, 4)
    with pytest.raises(DataError, match="cost calculation exceeds the finite numeric range"):
        replay_cost(result, rates)


def test_nonfinite_replay_quantities_are_not_reported_as_money() -> None:
    source = SimulationResult(
        periods=3,
        total_demand=10.0,
        served_from_stock=4.0,
        fill_rate=0.4,
        stockout_periods=1,
        average_on_hand=1e308,
        orders_placed=1,
        max_backorder=0.0,
        lead_time_periods=0,
    )
    with pytest.raises(DataError, match="cost calculation exceeds"):
        replay_cost(source, CostRates(holding=1.0))


def test_total_cost_rejects_overflow_of_finite_individual_breakdowns() -> None:
    one = CostBreakdown(
        orders=1, unit_periods=0, units_short=0, ordering=1e308, holding=0, stockout=0
    )
    with pytest.raises(DataError, match="aggregated costs exceed"):
        total_cost([one, one])


def test_total_cost_rejects_nonfinite_sum_of_components() -> None:
    bad = CostBreakdown(
        orders=1,
        unit_periods=0,
        units_short=0,
        ordering=1e308,
        holding=1e308,
        stockout=0,
    )
    assert math.isinf(bad.total)
    with pytest.raises(DataError, match="cost calculation exceeds"):
        total_cost([bad])


@pytest.mark.parametrize("invalid", [math.inf, math.nan, 10**400, "not numeric"])
def test_total_cost_rejects_malformed_public_breakdowns(invalid: object) -> None:
    bad = CostBreakdown(
        orders=1,
        unit_periods=0,
        units_short=0,
        ordering=invalid,  # type: ignore[arg-type]
        holding=0,
        stockout=0,
    )
    with pytest.raises(DataError, match="cost calculation exceeds"):
        total_cost([bad])


def test_normal_replay_and_aggregation_remain_unchanged() -> None:
    source = simulate([4, 4, 6, 4], 4, 8, lead_time=1)
    breakdown = replay_cost(source, CostRates(order=10, holding=0.5, stockout=3))
    assert (breakdown.orders, breakdown.ordering, breakdown.holding, breakdown.stockout) == (
        2,
        20,
        7,
        6,
    )
    assert breakdown.total == 33
    aggregate = total_cost([breakdown, breakdown])
    assert (aggregate.orders, aggregate.ordering, aggregate.holding, aggregate.stockout) == (
        4,
        40,
        14,
        12,
    )
    assert aggregate.total == 66
    assert total_cost([]).total == 0
