"""Public bootstrap functions validate every possible protection interval."""

from __future__ import annotations

import math
import random
import re

import pytest

from inventory_policy_lab import bootstrap_safety_stock, residual_bootstrap_quantile


@pytest.mark.parametrize("method", ["demand", "residual"])
@pytest.mark.parametrize("invalid", [-1.0, math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("field", ["lead_time", "review_period", "lead_times"])
def test_invalid_interval_inputs_fail_before_bootstrap(
    method: str, invalid: float, field: str
) -> None:
    lead_time = invalid if field == "lead_time" else 1.0
    review_period = invalid if field == "review_period" else 0.0
    lead_times = (1.0, invalid) if field == "lead_times" else (1.0,)
    label = "lead_times[1]" if field == "lead_times" else field
    rng = random.Random(27)
    prior_state = rng.getstate()
    with pytest.raises(ValueError, match=re.escape(f"{label} must be finite and non-negative")):
        if method == "demand":
            bootstrap_safety_stock(
                [2.0, 4.0],
                0.9,
                3.0,
                lead_time=lead_time,
                review_period=review_period,
                lead_times=lead_times,
                samples=20,
                rng=rng,
            )
        else:
            residual_bootstrap_quantile(
                {1: (2.0,)},
                0.9,
                lead_time=lead_time,
                review_period=review_period,
                lead_times=lead_times,
                samples=20,
                rng=rng,
            )
    assert rng.getstate() == prior_state


def test_valid_zero_intervals_remain_exact_and_reproducible() -> None:
    demand = bootstrap_safety_stock(
        [3.0, 5.0],
        0.95,
        4.0,
        lead_time=0.0,
        review_period=0.0,
        lead_times=(0.0,),
        samples=10,
        rng=random.Random(1),
    )
    assert demand == (0.0, 0.0)
    residual = residual_bootstrap_quantile(
        {},
        0.95,
        lead_time=0.0,
        review_period=0.0,
        lead_times=(0.0,),
        samples=10,
        rng=random.Random(1),
    )
    assert residual == 0.0


def test_valid_positive_interval_outputs_are_unchanged() -> None:
    demand = bootstrap_safety_stock(
        [5.0],
        0.4,
        5.0,
        lead_time=1.0,
        review_period=0.0,
        lead_times=(1.0,),
        samples=10,
        rng=random.Random(11),
    )
    assert demand == (5.0, 0.0)
    residual = residual_bootstrap_quantile(
        {1: (2.0,)},
        0.4,
        lead_time=1.0,
        review_period=0.0,
        lead_times=(1.0,),
        samples=10,
        rng=random.Random(11),
    )
    assert residual == 2.0


@pytest.mark.parametrize("method", ["demand", "residual"])
def test_bad_samples_keep_existing_error_priority(method: str) -> None:
    with pytest.raises(ValueError, match="samples must be at least 1"):
        if method == "demand":
            bootstrap_safety_stock([5.0], 0.95, 5.0, lead_time=math.inf, samples=0)
        else:
            residual_bootstrap_quantile({}, 0.95, lead_time=math.inf, samples=0)
