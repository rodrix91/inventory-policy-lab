"""Demand-path sampling fails closed on invalid numerical inputs."""

from __future__ import annotations

import math
import random
from typing import Any

import pytest

from inventory_policy_lab.optimize import demand_paths


@pytest.mark.parametrize("field", ["forecasts", "errors"])
@pytest.mark.parametrize(
    "invalid",
    [math.nan, math.inf, -math.inf, True, False, "1.0", None, 1 + 2j, 10**400],
)
def test_invalid_inputs_fail_before_random_sampling(field: str, invalid: Any) -> None:
    forecasts: list[Any] = [2.0, 3.0]
    errors: list[Any] = [-1.0, 1.0]
    (forecasts if field == "forecasts" else errors)[1] = invalid
    rng = random.Random(25)
    before = rng.getstate()

    with pytest.raises(ValueError, match=rf"{field}\[1\] must be finite and numeric"):
        demand_paths(forecasts, errors, 5, rng)

    assert rng.getstate() == before


def test_adding_finite_forecasts_and_errors_cannot_create_infinite_demand() -> None:
    rng = random.Random(31)
    before = rng.getstate()
    with pytest.raises(ValueError, match="combination produces non-finite demand"):
        demand_paths([1e308], [1e308], 4, rng)
    assert rng.getstate() == before


def test_signed_residuals_and_zero_floor_remain_reproducible() -> None:
    first = demand_paths([2.0, 10.0], [-5.0, 3.0], 20, random.Random(7))
    second = demand_paths([2.0, 10.0], [-5.0, 3.0], 20, random.Random(7))
    assert first == second
    assert all(math.isfinite(value) and value >= 0 for path in first for value in path)
    assert {value for path in first for value in path} >= {0.0, 5.0, 13.0}


def test_empty_errors_and_invalid_samples_keep_existing_diagnostics() -> None:
    with pytest.raises(ValueError, match="at least one error"):
        demand_paths([1.0], [], 1, random.Random(2))
    with pytest.raises(ValueError, match="sample count must be a positive integer"):
        demand_paths([1.0], [0.0], 0, random.Random(2))
