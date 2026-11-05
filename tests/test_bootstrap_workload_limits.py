"""Bootstrap budgets reject unbounded sampling before consuming RNG state."""

from __future__ import annotations

import math
import random

import pytest

from inventory_policy_lab import bootstrap_safety_stock, residual_bootstrap_quantile
from inventory_policy_lab.errors import DataError
from inventory_policy_lab.policy import (
    MAX_BOOTSTRAP_DEMAND_DRAWS,
    MAX_BOOTSTRAP_SAMPLES,
    _check_bootstrap_samples,
)


def test_maximum_sample_count_is_accepted_without_running_a_large_simulation() -> None:
    _check_bootstrap_samples(MAX_BOOTSTRAP_SAMPLES)
    with pytest.raises(ValueError, match="samples exceeds"):
        _check_bootstrap_samples(MAX_BOOTSTRAP_SAMPLES + 1)


@pytest.mark.parametrize("method", ["demand", "residual"])
def test_excessive_sample_count_is_refused_without_advancing_rng(method: str) -> None:
    rng = random.Random(2026)
    prior = rng.getstate()
    with pytest.raises(ValueError, match="samples exceeds"):
        if method == "demand":
            bootstrap_safety_stock(
                [1.0, 2.0], 0.95, 1.5, lead_time=1.0,
                samples=MAX_BOOTSTRAP_SAMPLES + 1, rng=rng,
            )
        else:
            residual_bootstrap_quantile(
                {1: (1.0, 2.0)}, 0.95, lead_time=1.0,
                samples=MAX_BOOTSTRAP_SAMPLES + 1, rng=rng,
            )
    assert rng.getstate() == prior


def test_extreme_finite_lead_time_cannot_allocate_unbounded_demand_samples() -> None:
    rng = random.Random(123)
    prior = rng.getstate()
    samples = 10
    too_many_periods = MAX_BOOTSTRAP_DEMAND_DRAWS // samples + 1
    with pytest.raises(DataError, match="bootstrap demand sampling exceeds"):
        bootstrap_safety_stock(
            [0.0], 0.95, 0.0, lead_time=float(too_many_periods),
            samples=samples, rng=rng,
        )
    assert rng.getstate() == prior


def test_every_potential_lead_time_is_checked_before_random_sampling() -> None:
    rng = random.Random(123)
    prior = rng.getstate()
    with pytest.raises(DataError, match="bootstrap demand sampling exceeds"):
        bootstrap_safety_stock(
            [2.0], 0.9, 0.0, lead_time=1.0, lead_times=(1.0, 2001.0),
            samples=1000, rng=rng,
        )
    assert rng.getstate() == prior


def test_combined_interval_overflow_is_rejected_before_random_sampling() -> None:
    rng = random.Random(123)
    prior = rng.getstate()
    with pytest.raises(DataError, match="sampled protection interval exceeds"):
        bootstrap_safety_stock(
            [0.0], 0.95, 0.0, lead_time=0.0,
            review_period=1e308, lead_times=(1e308,),
            samples=10, rng=rng,
        )
    assert rng.getstate() == prior


def test_seeded_normal_and_zero_interval_samples_remain_reproducible() -> None:
    first = bootstrap_safety_stock(
        [0.0, 5.0, 10.0], 0.9, 5.0, lead_time=2.0,
        samples=50, rng=random.Random(17),
    )
    second = bootstrap_safety_stock(
        [0.0, 5.0, 10.0], 0.9, 5.0, lead_time=2.0,
        samples=50, rng=random.Random(17),
    )
    assert first == second
    assert all(math.isfinite(value) for value in first)
    assert bootstrap_safety_stock(
        [1.0], 0.9, 1.0, lead_time=0.0, samples=10,
    ) == (0.0, 0.0)
