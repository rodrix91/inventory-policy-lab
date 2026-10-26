"""Direct inventory replay must reject impossible demand before modifying inventory."""

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
@pytest.mark.parametrize("invalid", [-0.1, -1.0, math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("position", [0, 2])
def test_invalid_demand_is_rejected_even_during_warmup(
    replay: Callable[..., SimulationResult],
    settings: dict[str, Any],
    invalid: float,
    position: int,
) -> None:
    data = [1.0, 2.0, 3.0]
    data[position] = invalid
    # The first two periods are unscored but must still be valid.
    with pytest.raises(
        ValueError, match=rf"demand\[{position}\] must be finite and non-negative"
    ):
        replay(data, lead_time=0.0, warmup=2, **settings)


@pytest.mark.parametrize(("replay", "settings"), REPLAYS)
def test_zero_and_valid_demand_preserve_replay_results(
    replay: Callable[..., SimulationResult], settings: dict[str, Any]
) -> None:
    actual = replay([0.0, 1.0, 2.0], lead_time=0.0, **settings)
    assert actual.periods == 3
    assert actual.total_demand == 3.0
    assert actual.served_from_stock == 3.0
    assert actual.fill_rate == 1.0
    all_zero = replay([0.0, 0.0, 0.0], lead_time=0.0, **settings)
    assert all_zero.total_demand == 0.0
    assert all_zero.fill_rate is None


def test_existing_input_error_precedence_is_preserved() -> None:
    with pytest.raises(ValueError, match="order_quantity must be positive"):
        simulate([-1.0], reorder_point=3.0, order_quantity=0.0, lead_time=0.0)
    with pytest.raises(ValueError, match="review_period must be at least 1"):
        simulate_periodic([-1.0], order_up_to=5.0, review_period=0, lead_time=0.0)
    with pytest.raises(ValueError, match="order_quantity must be positive"):
        simulate_rss(
            [-1.0], reorder_point=3.0, order_quantity=0.0, review_period=2, lead_time=0.0
        )


def test_invalid_demand_is_checked_before_any_period_can_be_scored() -> None:
    with pytest.raises(ValueError, match=r"demand\[0\] must be finite and non-negative"):
        simulate([math.nan, 1.0], reorder_point=2.0, order_quantity=1.0, lead_time=0.0, warmup=2)
