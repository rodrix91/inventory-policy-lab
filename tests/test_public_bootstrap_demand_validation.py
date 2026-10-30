"""Reject impossible demand in public safety-stock bootstrap before sampling."""

from __future__ import annotations

import math
import random

import pytest

from inventory_policy_lab import bootstrap_safety_stock


@pytest.mark.parametrize("invalid", [-1.0, -0.01, math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("position", [0, 2])
def test_invalid_observed_demand_is_rejected_at_original_position(
    position: int, invalid: float
) -> None:
    history = [1.0, 0.0, 5.0]
    history[position] = invalid
    rng = random.Random(33)
    state = rng.getstate()
    with pytest.raises(ValueError, match=rf"demand\[{position}\] must be finite and non-negative"):
        bootstrap_safety_stock(history, 0.9, 2.0, lead_time=2.0, samples=12, rng=rng)
    assert rng.getstate() == state


@pytest.mark.parametrize("invalid", [-1.0, -0.01, math.nan, math.inf, -math.inf])
def test_invalid_forecast_demand_is_rejected_before_sampling(invalid: float) -> None:
    rng = random.Random(18)
    state = rng.getstate()
    with pytest.raises(ValueError, match="demand_per_period must be finite and non-negative"):
        bootstrap_safety_stock([2.0, 0.0, 4.0], 0.95, invalid, lead_time=2.0, samples=12, rng=rng)
    assert rng.getstate() == state


@pytest.mark.parametrize("invalid", [-1.0, math.nan, math.inf, -math.inf])
def test_invalid_values_fail_even_when_interval_rounds_to_zero(invalid: float) -> None:
    with pytest.raises(ValueError, match=r"demand\[1\] must be finite and non-negative"):
        bootstrap_safety_stock([1.0, invalid], 0.9, 1.0, lead_time=0.0, samples=2)
    with pytest.raises(ValueError, match="demand_per_period must be finite and non-negative"):
        bootstrap_safety_stock([1.0, 0.0], 0.9, invalid, lead_time=0.0, samples=2)


def test_zero_and_intermittent_demand_preserve_hand_computed_outputs() -> None:
    quantile, safety = bootstrap_safety_stock(
        [0.0, 4.0],
        1.0,
        2.0,
        lead_time=1.0,
        samples=4,
        rng=random.Random(5),
    )
    assert quantile in (0.0, 4.0)
    assert safety == max(quantile - 2.0, 0.0)
    assert bootstrap_safety_stock(
        [0.0, 0.0],
        0.9,
        0.0,
        lead_time=2.0,
        samples=5,
        rng=random.Random(5),
    ) == (0.0, 0.0)
    assert bootstrap_safety_stock(
        [3.0, 5.0],
        0.95,
        4.0,
        lead_time=0.0,
        review_period=0.0,
        samples=5,
    ) == (0.0, 0.0)


def test_valid_bootstrap_keeps_seeded_reproducibility() -> None:
    a = bootstrap_safety_stock(
        [1.0, 0.0, 8.0, 2.0],
        0.95,
        2.75,
        lead_time=2.0,
        review_period=1.0,
        samples=24,
        rng=random.Random(8),
    )
    b = bootstrap_safety_stock(
        [1.0, 0.0, 8.0, 2.0],
        0.95,
        2.75,
        lead_time=2.0,
        review_period=1.0,
        samples=24,
        rng=random.Random(8),
    )
    assert a == b
    assert all(math.isfinite(value) and value >= 0 for value in a)


def test_existing_error_priority_for_bad_samples_and_service_is_preserved() -> None:
    with pytest.raises(ValueError, match="samples must be at least 1"):
        bootstrap_safety_stock([-1.0], 0.0, math.inf, lead_time=1.0, samples=0)
    with pytest.raises(ValueError, match="bootstrap service_level"):
        bootstrap_safety_stock([-1.0], 0.0, math.inf, lead_time=1.0)
    with pytest.raises(ValueError, match="lead_time must be finite and non-negative"):
        bootstrap_safety_stock([-1.0], 0.9, math.inf, lead_time=-1.0)
    with pytest.raises(ValueError, match="demand history is empty"):
        bootstrap_safety_stock([], 0.9, math.inf, lead_time=1.0)
