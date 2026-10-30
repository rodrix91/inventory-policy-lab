"""Public inventory replay APIs reject non-finite policy levels before scoring."""

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
@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf])
def test_scalar_policy_level_rejects_nonfinite(
    replay: Callable[..., SimulationResult], settings: dict[str, Any], invalid: float
) -> None:
    name = "order_up_to" if replay is simulate_periodic else "reorder_point"
    with pytest.raises(ValueError, match=rf"{name} must be finite"):
        replay([1.0, 0.0, 2.0], lead_time=0.0, **{**settings, name: invalid})


@pytest.mark.parametrize(("replay", "settings"), REPLAYS)
@pytest.mark.parametrize("position", [0, 2])
@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf])
def test_dynamic_policy_level_rejects_nonfinite_at_original_period(
    replay: Callable[..., SimulationResult],
    settings: dict[str, Any],
    position: int,
    invalid: float,
) -> None:
    name = "order_up_to" if replay is simulate_periodic else "reorder_point"
    levels = [3.0, 4.0, 5.0]
    levels[position] = invalid
    with pytest.raises(ValueError, match=rf"{name}\\[{position}\\] must be finite"):
        replay([1.0, 0.0, 2.0], lead_time=0.0, warmup=2, **{**settings, name: levels})


@pytest.mark.parametrize("replay", [simulate, simulate_rss])
@pytest.mark.parametrize("invalid", [math.nan, math.inf])
def test_scalar_order_quantity_rejects_nonfinite(
    replay: Callable[..., SimulationResult], invalid: float
) -> None:
    kwargs: dict[str, Any] = {"review_period": 2} if replay is simulate_rss else {}
    with pytest.raises(ValueError, match="order_quantity must be finite"):
        replay([1.0, 2.0], reorder_point=3.0, order_quantity=invalid, lead_time=0.0, **kwargs)


@pytest.mark.parametrize("replay", [simulate, simulate_rss])
@pytest.mark.parametrize("position", [0, 2])
@pytest.mark.parametrize("invalid", [math.nan, math.inf])
def test_dynamic_order_quantity_rejects_nonfinite_at_original_period(
    replay: Callable[..., SimulationResult], position: int, invalid: float
) -> None:
    kwargs: dict[str, Any] = {"review_period": 2} if replay is simulate_rss else {}
    quantities = [2.0, 2.0, 2.0]
    quantities[position] = invalid
    with pytest.raises(ValueError, match=rf"order_quantity\\[{position}\\] must be finite"):
        replay(
            [1.0, 2.0, 0.0],
            reorder_point=3.0,
            order_quantity=quantities,
            lead_time=0.0,
            warmup=2,
            **kwargs,
        )


@pytest.mark.parametrize(("replay", "settings"), REPLAYS)
def test_valid_dynamic_levels_preserve_existing_replay(
    replay: Callable[..., SimulationResult], settings: dict[str, Any]
) -> None:
    scalar = replay([1.0, 2.0, 0.0], lead_time=0.0, **settings)
    dynamic: dict[str, Any] = {
        name: [value] * 3 if name in ("reorder_point", "order_up_to", "order_quantity") else value
        for name, value in settings.items()
    }
    assert replay([1.0, 2.0, 0.0], lead_time=0.0, **dynamic) == scalar


@pytest.mark.parametrize(("replay", "settings"), REPLAYS)
def test_nonfinite_policy_level_rejected_even_without_scored_periods(
    replay: Callable[..., SimulationResult], settings: dict[str, Any]
) -> None:
    name = "order_up_to" if replay is simulate_periodic else "reorder_point"
    with pytest.raises(ValueError, match=rf"{name} must be finite"):
        replay([], lead_time=0.0, **{**settings, name: math.nan})
