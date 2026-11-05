"""Reject excessive bootstrap sampling work before drawing or allocating lists."""

from __future__ import annotations

import random

import pytest

import inventory_policy_lab.policy as policy
from inventory_policy_lab import bootstrap_safety_stock
from inventory_policy_lab.errors import DataError


def test_large_finite_horizon_fails_before_any_random_draw() -> None:
    rng = random.Random(51)
    prior = rng.getstate()
    with pytest.raises(ValueError, match="bootstrap demand sampling exceeds"):
        bootstrap_safety_stock([0.0], 0.95, 0.0, lead_time=1e308, samples=3, rng=rng)
    assert rng.getstate() == prior


def test_unselected_extreme_lead_time_cannot_evade_workload_guard() -> None:
    rng = random.Random(52)
    prior = rng.getstate()
    with pytest.raises(ValueError, match="bootstrap demand sampling exceeds"):
        bootstrap_safety_stock(
            [0.0, 2.0],
            0.95,
            1.0,
            lead_time=1.0,
            lead_times=(0.0, 1e308),
            samples=4,
            rng=rng,
        )
    assert rng.getstate() == prior


def test_overflowing_possible_sample_interval_is_controlled() -> None:
    rng = random.Random(53)
    prior = rng.getstate()
    with pytest.raises(DataError, match="sampled interval duration exceeds"):
        bootstrap_safety_stock(
            [0.0],
            0.95,
            0.0,
            lead_time=0.0,
            review_period=1e308,
            lead_times=(1e308,),
            samples=1,
            rng=rng,
        )
    assert rng.getstate() == prior


def test_exact_budget_accepts_previous_results_and_rejects_next_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(policy, "MAX_BOOTSTRAP_DEMAND_DRAWS", 12)
    first = bootstrap_safety_stock(
        [2.0],
        0.95,
        2.0,
        lead_time=3.0,
        samples=4,
        rng=random.Random(54),
    )
    second = bootstrap_safety_stock(
        [2.0],
        0.95,
        2.0,
        lead_time=3.0,
        samples=4,
        rng=random.Random(54),
    )
    assert first == second == (6.0, 0.0)
    rng = random.Random(54)
    before = rng.getstate()
    with pytest.raises(ValueError, match="exceeds 12 draw-periods"):
        bootstrap_safety_stock(
            [2.0],
            0.95,
            2.0,
            lead_time=4.0,
            samples=4,
            rng=rng,
        )
    assert rng.getstate() == before


def test_zero_horizon_still_limits_result_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(policy, "MAX_BOOTSTRAP_DEMAND_DRAWS", 12)
    assert bootstrap_safety_stock([0.0], 0.95, 0.0, lead_time=0.0, samples=12) == (0.0, 0.0)
    rng = random.Random(55)
    prior = rng.getstate()
    with pytest.raises(ValueError, match="exceeds 12 draw-periods"):
        bootstrap_safety_stock([0.0], 0.95, 0.0, lead_time=0.0, samples=13, rng=rng)
    assert rng.getstate() == prior
