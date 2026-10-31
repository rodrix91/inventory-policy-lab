"""Public bootstraps fail closed on malformed types before advancing random state."""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from typing import Any

import pytest

from inventory_policy_lab import bootstrap_safety_stock, residual_bootstrap_quantile


def _demand(**overrides: Any) -> tuple[float, float]:
    params: dict[str, Any] = {
        "demand": [2.0, 4.0],
        "service_level": 0.95,
        "demand_per_period": 3.0,
        "lead_time": 1.0,
        "samples": 8,
    }
    params.update(overrides)
    return bootstrap_safety_stock(**params)


def _residual(**overrides: Any) -> float:
    params: dict[str, Any] = {
        "errors": {1: (-2.0, 3.0)},
        "service_level": 0.95,
        "lead_time": 1.0,
        "samples": 8,
    }
    params.update(overrides)
    return residual_bootstrap_quantile(**params)


Runner = Callable[..., object]
BAD_NUMBERS: tuple[Any, ...] = (True, False, "1", None, 1 + 2j, object(), 10**400)


@pytest.mark.parametrize("runner", [_demand, _residual])
@pytest.mark.parametrize("samples", [True, False, 0, -1, 1.5, 2.0, "2", None, object()])
def test_sample_count_must_be_an_actual_positive_integer(
    runner: Runner, samples: Any
) -> None:
    rng = random.Random(33)
    state = rng.getstate()
    with pytest.raises(ValueError, match="samples must be at least 1"):
        runner(samples=samples, rng=rng)
    assert rng.getstate() == state


@pytest.mark.parametrize("runner", [_demand, _residual])
@pytest.mark.parametrize("level", [*BAD_NUMBERS, 0.0, 1.01, math.nan, math.inf])
def test_service_level_rejects_malformed_and_out_of_range_values(
    runner: Runner, level: Any
) -> None:
    rng = random.Random(34)
    state = rng.getstate()
    with pytest.raises(ValueError, match=r"bootstrap service_level must be in \(0, 1\]"):
        runner(service_level=level, rng=rng)
    assert rng.getstate() == state


@pytest.mark.parametrize("runner", [_demand, _residual])
@pytest.mark.parametrize("field", ["lead_time", "review_period"])
@pytest.mark.parametrize("value", BAD_NUMBERS)
def test_malformed_protection_intervals_have_parameter_specific_errors(
    runner: Runner, field: str, value: Any
) -> None:
    rng = random.Random(35)
    state = rng.getstate()
    with pytest.raises(ValueError, match=f"{field} must be finite and non-negative"):
        runner(**{field: value}, rng=rng)
    assert rng.getstate() == state


@pytest.mark.parametrize("runner", [_demand, _residual])
@pytest.mark.parametrize("value", BAD_NUMBERS)
def test_malformed_lead_time_observations_are_rejected_before_sampling(
    runner: Runner, value: Any
) -> None:
    rng = random.Random(36)
    state = rng.getstate()
    with pytest.raises(ValueError, match=r"lead_times\[1\] must be finite and non-negative"):
        runner(lead_times=(1.0, value), rng=rng)
    assert rng.getstate() == state


@pytest.mark.parametrize("value", BAD_NUMBERS)
def test_malformed_historical_demand_is_rejected_at_original_index(value: Any) -> None:
    rng = random.Random(37)
    state = rng.getstate()
    with pytest.raises(ValueError, match=r"demand\[1\] must be finite and non-negative"):
        _demand(demand=[1.0, value], rng=rng)
    assert rng.getstate() == state


@pytest.mark.parametrize("value", BAD_NUMBERS)
def test_malformed_forecast_demand_is_rejected_before_sampling(value: Any) -> None:
    rng = random.Random(38)
    state = rng.getstate()
    with pytest.raises(ValueError, match="demand_per_period must be finite and non-negative"):
        _demand(demand_per_period=value, rng=rng)
    assert rng.getstate() == state


@pytest.mark.parametrize("value", BAD_NUMBERS)
def test_malformed_reachable_residuals_are_rejected_before_sampling(value: Any) -> None:
    rng = random.Random(39)
    state = rng.getstate()
    with pytest.raises(ValueError, match=r"errors\[1\]\[1\] must be finite"):
        _residual(errors={1: (-2.0, value)}, rng=rng)
    assert rng.getstate() == state


def test_valid_integer_sample_counts_and_finite_negative_residuals_still_work() -> None:
    assert _demand(samples=1, demand=[3.0], demand_per_period=3.0) == (3.0, 0.0)
    assert _residual(samples=1, errors={1: (-3.0,)}) == -3.0
    assert _demand(samples=4, service_level=1.0, lead_time=0.0) == (0.0, 0.0)
    assert _residual(samples=4, service_level=1.0, lead_time=0.0) == 0.0
