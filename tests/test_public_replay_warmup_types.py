"""A replay's warmup must be a real count, never a fractional or boolean period."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import pytest

from inventory_policy_lab import SimulationResult, simulate, simulate_periodic, simulate_rss

REPLAYS: tuple[tuple[Callable[..., SimulationResult], dict[str, Any]], ...] = (
    (simulate, {"reorder_point": 3.0, "order_quantity": 2.0}),
    (simulate_periodic, {"order_up_to": 5.0, "review_period": 2}),
    (simulate_rss, {"reorder_point": 3.0, "order_quantity": 2.0, "review_period": 2}),
)


@pytest.mark.parametrize(("replay", "settings"), REPLAYS)
@pytest.mark.parametrize(
    "invalid", [True, False, 1.0, 1.5, "1", None, math.nan, math.inf, -math.inf, object()]
)
def test_reject_invalid_warmup_types_before_processing_demand(
    replay: Callable[..., SimulationResult], settings: dict[str, Any], invalid: Any
) -> None:
    with pytest.raises(ValueError, match="warmup must be an integer number of periods"):
        replay([-1.0, 2.0, 3.0], warmup=invalid, lead_time=0.0, **settings)


@pytest.mark.parametrize(("replay", "settings"), REPLAYS)
@pytest.mark.parametrize("invalid", [-1, 4])
def test_out_of_range_integer_preserves_existing_error(
    replay: Callable[..., SimulationResult], settings: dict[str, Any], invalid: int
) -> None:
    with pytest.raises(ValueError, match="warmup must be between 0 and the number of periods"):
        replay([-1.0, 2.0, 3.0], warmup=invalid, lead_time=0.0, **settings)


@pytest.mark.parametrize(("replay", "settings"), REPLAYS)
@pytest.mark.parametrize(
    ("warmup", "count", "total"),
    [(0, 3, 6.0), (1, 2, 5.0), (3, 0, 0.0)],
)
def test_integer_warmup_preserves_scored_periods_and_demand(
    replay: Callable[..., SimulationResult],
    settings: dict[str, Any],
    warmup: int,
    count: int,
    total: float,
) -> None:
    result = replay([1.0, 2.0, 3.0], warmup=warmup, lead_time=0.0, **settings)
    assert result.periods == count
    assert result.total_demand == total
    assert (result.fill_rate is None) == (warmup == 3)
