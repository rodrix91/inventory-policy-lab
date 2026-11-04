"""Direct bootstrap callers get validated origins and finite demand before any RNG draw."""

from __future__ import annotations

import math
import random
from typing import Any

import pytest

from inventory_policy_lab.optimize import block_bootstrap, bootstrap_histories

SERIES = [5.0, 6.0, 12.0, 9.0]
FORECASTS = [(2, 10.0), (3, 10.0)]


@pytest.mark.parametrize(
    ("origins", "message"),
    [
        ([(2, 10.0), (2, 10.0)], "strictly increasing"),
        ([(3, 10.0), (2, 10.0)], "strictly increasing"),
        ([(0, 10.0), (2, 10.0)], "in-range"),
        ([(-1, 10.0), (2, 10.0)], "in-range"),
        ([(2, 10.0), (4, 10.0)], "in-range"),
        ([(True, 10.0), (2, 10.0)], "in-range"),
        ([(2.0, 10.0), (3, 10.0)], "in-range"),
    ],
)
def test_rejects_invalid_forecast_origins_before_sampling(
    origins: list[tuple[Any, float]], message: str
) -> None:
    rng = random.Random(41)
    state = rng.getstate()
    with pytest.raises(ValueError, match=message):
        bootstrap_histories(SERIES, origins, 3, rng)
    assert rng.getstate() == state


@pytest.mark.parametrize("index", [0, 3])
@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf, -1.0, True, "1"])
def test_invalid_source_demand_fails_before_random_sampling(index: int, invalid: Any) -> None:
    values: list[Any] = list(SERIES)
    values[index] = invalid
    rng = random.Random(41)
    state = rng.getstate()
    with pytest.raises(ValueError, match=rf"series\[{index}\]"):
        bootstrap_histories(values, FORECASTS, 3, rng)
    assert rng.getstate() == state


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf, -1.0, True, "1"])
def test_invalid_one_step_forecast_fails_before_random_sampling(index: int, invalid: Any) -> None:
    values: list[tuple[int, Any]] = list(FORECASTS)
    values[index] = (FORECASTS[index][0], invalid)
    rng = random.Random(41)
    state = rng.getstate()
    with pytest.raises(ValueError, match=rf"one_step\[{index}\] forecast"):
        bootstrap_histories(SERIES, values, 3, rng)
    assert rng.getstate() == state


def test_all_possible_residual_combinations_must_stay_finite() -> None:
    rng = random.Random(51)
    state = rng.getstate()
    with pytest.raises(ValueError, match="combination produces non-finite demand"):
        bootstrap_histories([0.0, 0.0, 0.0, 1e308], [(2, 1e308), (3, 0.0)], 2, rng)
    assert rng.getstate() == state


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf, True, "1", 10**400])
def test_public_block_bootstrap_rejects_invalid_residuals(invalid: Any) -> None:
    rng = random.Random(61)
    state = rng.getstate()
    with pytest.raises(ValueError, match=r"errors\[1\] must be finite and numeric"):
        block_bootstrap([-1.0, invalid, 3.0], 4, 2, rng)
    assert rng.getstate() == state


def test_normal_bootstrap_is_seeded_and_preserves_untouched_history() -> None:
    first = bootstrap_histories(SERIES, FORECASTS, 8, random.Random(71))
    second = bootstrap_histories(SERIES, FORECASTS, 8, random.Random(71))
    assert first == second
    assert len(first) == 8
    assert all(len(row) == len(SERIES) and row[:2] == tuple(SERIES[:2]) for row in first)
    assert all(math.isfinite(value) and value >= 0 for row in first for value in row)
    assert block_bootstrap([-1.0, 2.0, -3.0], 5, 2, random.Random(19)) == block_bootstrap(
        [-1.0, 2.0, -3.0], 5, 2, random.Random(19)
    )
