"""Reject non-finite forecast residuals before any public bootstrap draws."""

from __future__ import annotations

import math
import random
import re

import pytest

from inventory_policy_lab import residual_bootstrap_quantile


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("period", [1, 2])
@pytest.mark.parametrize("index", [0, 2])
def test_reachable_nonfinite_residual_is_indexed_and_rejected_before_random_draw(
    invalid: float, period: int, index: int
) -> None:
    values = [-3.0, 0.0, 6.0]
    values[index] = invalid
    errors = {1: (-2.0, 1.0), 2: (-4.0, 2.0)}
    errors[period] = tuple(values)
    rng = random.Random(7)
    state = rng.getstate()
    message = re.escape(f"errors[{period}][{index}] must be finite")
    with pytest.raises(ValueError, match=message):
        residual_bootstrap_quantile(
            errors,
            0.95,
            lead_time=1.0,
            lead_times=(1.0, 2.0),
            samples=20,
            rng=rng,
        )
    assert rng.getstate() == state


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf])
def test_nonfinite_residual_in_unreachable_interval_is_ignored(invalid: float) -> None:
    quantile = residual_bootstrap_quantile(
        {1: (-2.0,), 3: (invalid,)},
        0.95,
        lead_time=1.0,
        samples=5,
        rng=random.Random(3),
    )
    assert quantile == -2.0


def test_zero_period_needs_no_residuals_and_does_not_read_unused_values() -> None:
    assert residual_bootstrap_quantile(
        {0: (math.nan,), 1: (math.inf,)},
        0.95,
        lead_time=0.0,
        samples=5,
        rng=random.Random(3),
    ) == 0.0


def test_negative_finite_residuals_and_seeded_draws_are_unchanged() -> None:
    values = {1: (-3.0, -1.0, 2.0)}
    first = residual_bootstrap_quantile(
        values, 0.95, lead_time=1.0, samples=30, rng=random.Random(4)
    )
    second = residual_bootstrap_quantile(
        values, 0.95, lead_time=1.0, samples=30, rng=random.Random(4)
    )
    assert first == second == 2.0
    assert residual_bootstrap_quantile(
        {1: (-3.0,)}, 1.0, lead_time=1.0, samples=5
    ) == -3.0


def test_missing_reachable_interval_keeps_original_error_priority() -> None:
    rng = random.Random(12)
    state = rng.getstate()
    with pytest.raises(ValueError, match=r"no forecast errors over 2 period\(s\)"):
        residual_bootstrap_quantile(
            {1: (math.nan,)},
            0.95,
            lead_time=1.0,
            lead_times=(1.0, 2.0),
            samples=4,
            rng=rng,
        )
    assert rng.getstate() == state


def test_earlier_sample_service_and_lead_time_checks_keep_priority() -> None:
    invalid = {1: (math.nan,)}
    with pytest.raises(ValueError, match="samples must be at least 1"):
        residual_bootstrap_quantile(invalid, 0.0, lead_time=-1.0, samples=0)
    with pytest.raises(ValueError, match="bootstrap service_level"):
        residual_bootstrap_quantile(invalid, 0.0, lead_time=-1.0)
    with pytest.raises(ValueError, match="lead_time must be finite and non-negative"):
        residual_bootstrap_quantile(invalid, 0.95, lead_time=-1.0)
