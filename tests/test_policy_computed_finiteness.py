"""Computed stock levels must stay finite even for individually valid inputs."""

from __future__ import annotations

import math

import pytest

from inventory_policy_lab import build_policy, safety_stock
from inventory_policy_lab.errors import DataError


@pytest.mark.parametrize(
    ("sigma_demand", "lead_time", "review_period"),
    [
        (1.2e308, 1.0, 0.0),
        (1e308, 1e308, 0.0),
        (1e308, 1e308, 1e308),
    ],
)
def test_normal_safety_stock_rejects_unrepresentable_calculated_result(
    sigma_demand: float,
    lead_time: float,
    review_period: float,
) -> None:
    # Inputs are all valid finite numbers, but z times the deviation is not.
    with pytest.raises(
        DataError, match="normal safety stock exceeds the finite numeric range"
    ):
        safety_stock(
            0.95,
            demand_per_period=0.0,
            sigma_demand=sigma_demand,
            lead_time=lead_time,
            review_period=review_period,
        )


def test_normal_policy_rejects_overflowed_safety_stock_before_publication() -> None:
    with pytest.raises(
        DataError, match="normal safety stock exceeds the finite numeric range"
    ):
        build_policy(0.95, demand_per_period=0, sigma_demand=1.2e308, lead_time=1)


@pytest.mark.parametrize("bootstrap_units", [None, 3.0])
def test_build_policy_rejects_overflowed_reorder_point(
    bootstrap_units: float | None,
) -> None:
    # The stock is representable, but D * L is larger than binary64.
    with pytest.raises(
        DataError, match="policy reorder point exceeds the finite numeric range"
    ):
        build_policy(
            0.95,
            demand_per_period=1e308,
            sigma_demand=0.0,
            lead_time=2.0,
            bootstrap_units=bootstrap_units,
        )


def test_half_service_level_keeps_zero_stock_but_rejects_overflowed_reorder() -> None:
    # With z = 0, the standalone stock estimate still has its documented
    # exact zero result even when variance intermediates overflow.
    assert safety_stock(0.5, 1e308, 1e308, 1e308, 1e308, 1e308) == (0.0, 0.0)
    with pytest.raises(
        DataError, match="policy reorder point exceeds the finite numeric range"
    ):
        build_policy(0.5, 1e308, 0.0, 2.0)


@pytest.mark.parametrize("bootstrap_units", [0.0, 7.5])
def test_valid_bootstrap_replaces_unused_overflowing_normal_stock(
    bootstrap_units: float,
) -> None:
    # The empirical stock is finite. Rejecting it solely because the
    # unused normal approximation overflows would be a compatibility bug.
    policy = build_policy(
        0.95,
        demand_per_period=0.0,
        sigma_demand=1.2e308,
        lead_time=1.0,
        bootstrap_units=bootstrap_units,
    )
    assert policy.safety_stock_method == "bootstrap"
    assert policy.safety_stock == bootstrap_units
    assert policy.reorder_point == bootstrap_units
    assert math.isfinite(policy.z)


def test_large_representable_results_still_work_normally() -> None:
    z, stock = safety_stock(0.95, 0.0, 1e308, 1.0)
    assert math.isfinite(z)
    assert stock == pytest.approx(z * 1e308)
    plain = build_policy(0.95, 5e307, 0.0, 2.0)
    assert plain.reorder_point == 1e308
    assert plain.safety_stock == 0.0
