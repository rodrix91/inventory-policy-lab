"""Prevent non-finite or imprecise multi-SKU replay summaries."""

from __future__ import annotations

import math

import pytest

from inventory_policy_lab.errors import DataError
from inventory_policy_lab.simulate import SimulationResult
from inventory_policy_lab.validation import _sum


def replay(
    demand: float,
    served: float,
    on_hand: float = 0.0,
    stockouts: int = 0,
) -> SimulationResult:
    return SimulationResult(
        periods=1,
        total_demand=demand,
        served_from_stock=served,
        fill_rate=served / demand if demand > 0 else None,
        stockout_periods=stockouts,
        average_on_hand=on_hand,
        orders_placed=0,
        max_backorder=0.0,
        lead_time_periods=0,
    )


def test_ordinary_and_empty_aggregates_keep_expected_totals() -> None:
    total = _sum([replay(10.0, 8.0, 4.0, 1), replay(6.0, 6.0, 2.0)])
    assert total.total_demand == 16.0
    assert total.served_from_stock == 14.0
    assert total.fill_rate == 14.0 / 16.0
    assert total.stockout_periods == 1
    assert total.average_on_hand == 6.0
    assert _sum([]).fill_rate is None


def test_preserves_small_sku_contributions_to_large_finite_totals() -> None:
    # Naive sum([1e16, 1, 1]) rounds away both small items.
    total = _sum([replay(1e16, 0, 1e16), replay(1, 0, 1), replay(1, 0, 1)])
    assert total.total_demand == 1e16 + 2
    assert total.average_on_hand == 1e16 + 2
    assert total.fill_rate == 0.0


@pytest.mark.parametrize(
    "items",
    [
        [replay(1e308, 1e308), replay(1e308, 1e308)],
        [replay(1.0, 1e308), replay(1.0, 1e308)],
        [replay(1.0, 0.0, 1e308), replay(1.0, 0.0, 1e308)],
    ],
)
def test_aggregation_overflow_is_a_controlled_data_error(
    items: list[SimulationResult],
) -> None:
    with pytest.raises(DataError, match="aggregated replay totals exceed"):
        _sum(items)


@pytest.mark.parametrize(
    "item",
    [
        replay(math.inf, 0.0),
        replay(math.nan, 0.0),
        replay(1.0, math.inf),
        replay(1.0, math.nan),
        replay(1.0, 0.0, math.inf),
        replay(1.0, 0.0, math.nan),
    ],
)
def test_nonfinite_input_totals_fail_closed(item: SimulationResult) -> None:
    with pytest.raises(DataError, match="aggregated replay totals must be finite"):
        _sum([item])


def test_large_but_representable_aggregate_remains_supported() -> None:
    total = _sum([replay(1e307, 0.5e307, 1e307), replay(1e307, 0.5e307, 1e307)])
    assert total.total_demand == 2e307
    assert total.served_from_stock == 1e307
    assert total.average_on_hand == 2e307
    assert total.fill_rate == 0.5
