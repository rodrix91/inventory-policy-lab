"""Standalone replay APIs reject invalid lead times without changing valid rounding."""

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
def test_public_replay_rejects_invalid_lead_times(
    replay: Callable[..., SimulationResult], settings: dict[str, Any], invalid: float
) -> None:
    with pytest.raises(ValueError, match="lead_time must be finite and non-negative"):
        replay([1.0, 2.0, 0.0], lead_time=invalid, **settings)


@pytest.mark.parametrize(("replay", "settings"), REPLAYS)
@pytest.mark.parametrize(
    ("lead_time", "rounded"), [(0.0, 0), (-0.0, 0), (0.49, 0), (0.5, 1), (1.49, 1), (1.5, 2)]
)
def test_public_replay_retains_half_up_rounding_for_valid_lead_times(
    replay: Callable[..., SimulationResult],
    settings: dict[str, Any],
    lead_time: float,
    rounded: int,
) -> None:
    result = replay([1.0, 0.0, 2.0], lead_time=lead_time, **settings)
    assert result.lead_time_periods == rounded
    assert result.periods == 3


def test_existing_argument_error_precedence_is_unchanged() -> None:
    with pytest.raises(ValueError, match="order_quantity must be positive"):
        simulate([1.0], reorder_point=3.0, order_quantity=0.0, lead_time=-1.0)
    with pytest.raises(ValueError, match="review_period must be at least 1"):
        simulate_periodic([1.0], order_up_to=3.0, review_period=0, lead_time=-1.0)
    with pytest.raises(ValueError, match="order_quantity must be positive"):
        simulate_rss([1.0], reorder_point=3.0, order_quantity=0.0, review_period=2, lead_time=-1.0)


def test_invalid_lead_time_is_rejected_even_without_scored_periods() -> None:
    with pytest.raises(ValueError, match="lead_time must be finite and non-negative"):
        simulate([], reorder_point=3.0, order_quantity=1.0, lead_time=math.nan)
