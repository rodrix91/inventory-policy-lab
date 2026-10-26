"""Public bootstrap APIs reject invalid nearest-rank quantile levels."""

from __future__ import annotations

import math
import random

import pytest

from inventory_policy_lab import bootstrap_safety_stock, residual_bootstrap_quantile


@pytest.mark.parametrize("level", [0.0, -0.2, 1.001, math.nan, math.inf, -math.inf])
def test_demand_bootstrap_rejects_invalid_service_levels(level: float) -> None:
    with pytest.raises(ValueError, match=r"bootstrap service_level must be in \(0, 1\]"):
        bootstrap_safety_stock([5.0, 10.0], level, 7.5, lead_time=1, samples=10)


@pytest.mark.parametrize("level", [0.0, -0.2, 1.001, math.nan, math.inf, -math.inf])
def test_residual_bootstrap_rejects_invalid_service_levels(level: float) -> None:
    with pytest.raises(ValueError, match=r"bootstrap service_level must be in \(0, 1\]"):
        residual_bootstrap_quantile({1: (5.0,)}, level, lead_time=1, samples=10)


@pytest.mark.parametrize("level", [0.3, 0.4, 0.6, 1.0])
def test_valid_quantile_levels_remain_supported(level: float) -> None:
    demand_quantile, stock = bootstrap_safety_stock(
        [5.0], level, 5.0, lead_time=1, samples=10, rng=random.Random(123)
    )
    assert demand_quantile == 5.0
    assert stock == 0.0
    assert residual_bootstrap_quantile(
        {1: (2.0,)}, level, lead_time=1, samples=10, rng=random.Random(123)
    ) == 2.0


def test_invalid_sample_count_retains_existing_precedence() -> None:
    with pytest.raises(ValueError, match="samples must be at least 1"):
        bootstrap_safety_stock([5.0], 0.0, 5.0, lead_time=1, samples=0)
    with pytest.raises(ValueError, match="samples must be at least 1"):
        residual_bootstrap_quantile({1: (2.0,)}, 0.0, lead_time=1, samples=0)
