"""Safety stock, reorder point and EOQ formulas."""

from __future__ import annotations

import math
from statistics import NormalDist

import pytest

from inventory_policy_lab import build_policy, eoq, safety_stock


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
