"""Safety stock, reorder point and EOQ formulas."""

from __future__ import annotations

import math
import random
from statistics import NormalDist

import pytest

from inventory_policy_lab import bootstrap_safety_stock, build_policy, eoq, safety_stock


def test_safety_stock_with_demand_variability_only() -> None:
    z, ss = safety_stock(0.95, demand_per_period=100, sigma_demand=20, lead_time=4)
    assert z == pytest.approx(1.6448536)
    assert ss == pytest.approx(1.6448536 * 20 * 2)  # z * sigma * sqrt(4)


def test_safety_stock_with_lead_time_variability_and_review_period() -> None:
    z, ss = safety_stock(0.9, 50, 10, lead_time=2, sigma_lead_time=0.5, review_period=1)
    expected = NormalDist().inv_cdf(0.9) * math.sqrt(3 * 10**2 + 50**2 * 0.5**2)
    assert ss == pytest.approx(expected)
    assert z == pytest.approx(1.2815516)


def test_service_level_of_one_half_needs_no_safety_stock() -> None:
    assert safety_stock(0.5, 10, 3, 2) == (0.0, 0.0)


def test_build_policy() -> None:
    policy = build_policy(0.95, 10, 2, lead_time=2, review_period=1, eoq_units=50)
    assert policy.reorder_point == pytest.approx(30 + policy.safety_stock)
    assert policy.safety_stock == pytest.approx(policy.z * 2 * math.sqrt(3))
    assert policy.eoq == 50
    continuous = build_policy(0.95, 10, 2, lead_time=2)
    assert continuous.review_period == 0
    assert continuous.reorder_point == pytest.approx(20 + continuous.z * 2 * math.sqrt(2))


def test_eoq() -> None:
    assert eoq(1200, 30, 0.5) == pytest.approx(math.sqrt(2 * 1200 * 30 / 0.5))
    assert eoq(120, 30, 0.5) == pytest.approx(120)
    assert eoq(0, 30, 0.5) is None
    assert eoq(100, 30, 0) is None


def test_bootstrap_of_a_constant_history_is_exact() -> None:
    quantile, ss = bootstrap_safety_stock([5.0] * 12, 0.95, 5.0, lead_time=2, review_period=1)
    assert quantile == 15.0
    assert ss == 0.0


def test_bootstrap_quantile_by_hand() -> None:
    # One-period interval over a 0/10 history: the 95% quantile is 10 unless
    # fewer than 5% of 1000 draws were 10, which a fair coin makes negligible.
    quantile, ss = bootstrap_safety_stock(
        [0.0, 10.0], 0.95, 5.0, lead_time=1, samples=1000, rng=random.Random(1)
    )
    assert quantile == 10.0
    assert ss == pytest.approx(5.0)
    low, _ = bootstrap_safety_stock(
        [0.0, 10.0], 0.4, 5.0, lead_time=1, samples=1000, rng=random.Random(1)
    )
    assert low == 0.0


def test_bootstrap_draws_observed_lead_times_and_is_seeded() -> None:
    history = [3.0, 0, 7, 1, 0, 12, 4, 0, 2, 9]
    a = bootstrap_safety_stock(history, 0.9, 3.8, 3, 1, (2, 4), rng=random.Random(42))
    b = bootstrap_safety_stock(history, 0.9, 3.8, 3, 1, (2, 4), rng=random.Random(42))
    assert a == b
    # A longer interval needs at least as much stock at the same quantile.
    short, _ = bootstrap_safety_stock(history, 0.9, 3.8, 1, rng=random.Random(42))
    assert a[0] >= short
    zero, _ = bootstrap_safety_stock(history, 0.9, 3.8, 0, review_period=0.2)
    assert zero == 0.0  # rounds to a zero-period interval


def test_bootstrap_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="samples"):
        bootstrap_safety_stock([1.0], 0.9, 1.0, 1, samples=0)
    with pytest.raises(ValueError, match="empty"):
        bootstrap_safety_stock([], 0.9, 1.0, 1)


def test_build_policy_with_bootstrap_units() -> None:
    policy = build_policy(0.95, 10, 2, lead_time=2, review_period=1, bootstrap_units=4.5)
    assert policy.safety_stock_method == "bootstrap"
    assert policy.safety_stock == 4.5
    assert policy.reorder_point == pytest.approx(34.5)
    assert build_policy(0.95, 10, 2, lead_time=2).safety_stock_method == "normal"
