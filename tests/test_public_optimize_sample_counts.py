"""Public stochastic optimization paths require an actual positive sample count."""

from __future__ import annotations

import random
from typing import cast

import pytest

from inventory_policy_lab.optimize import block_bootstrap, bootstrap_histories, demand_paths


@pytest.mark.parametrize("invalid", [False, True, 0, -1, 1.5, "3", None, [], {}])
@pytest.mark.parametrize("kind", ["forecast", "refit"])
def test_invalid_samples_fail_before_any_random_draw(invalid: object, kind: str) -> None:
    rng = random.Random(2026)
    before = rng.getstate()
    with pytest.raises(ValueError, match="sample count must be a positive integer"):
        if kind == "forecast":
            demand_paths([4.0, 5.0], [-2.0, 1.0], cast(int, invalid), rng)
        else:
            bootstrap_histories(
                [5.0, 6.0, 12.0, 9.0],
                [(2, 10.0), (3, 10.0)],
                cast(int, invalid),
                rng,
            )
    assert rng.getstate() == before


@pytest.mark.parametrize("count", [1, 3])
def test_valid_sample_count_keeps_deterministic_paths(count: int) -> None:
    first = demand_paths([4.0, 5.0], [-2.0, 1.0], count, random.Random(7))
    again = demand_paths([4.0, 5.0], [-2.0, 1.0], count, random.Random(7))
    assert first == again
    assert len(first) == count
    assert all(len(path) == 2 and all(value >= 0 for value in path) for path in first)

    series = [5.0, 6.0, 12.0, 9.0]
    one_step = [(2, 10.0), (3, 10.0)]
    boot = bootstrap_histories(series, one_step, count, random.Random(7))
    assert boot == bootstrap_histories(series, one_step, count, random.Random(7))
    assert len(boot) == count
    assert all(history[:2] == (5.0, 6.0) and len(history) == 4 for history in boot)


def test_existing_error_precedence_for_missing_data_is_preserved() -> None:
    with pytest.raises(ValueError, match="at least one error"):
        demand_paths([1.0], [], 0, random.Random(7))
    with pytest.raises(ValueError, match="at least two one-step forecasts"):
        bootstrap_histories([1.0, 2.0], [(1, 1.0)], 0, random.Random(7))


@pytest.mark.parametrize("invalid", [False, True, 0, -1, 1.5, "3", None, [], {}])
@pytest.mark.parametrize("parameter", ["length", "block"])
def test_block_bootstrap_rejects_invalid_integer_options_without_random_draws(
    invalid: object, parameter: str
) -> None:
    rng = random.Random(2026)
    state = rng.getstate()
    options = {"length": 4, "block": 2}
    options[parameter] = cast(int, invalid)
    with pytest.raises(ValueError, match=f"bootstrap {parameter} must be a positive integer"):
        block_bootstrap([1.0, -2.0, 3.0], options["length"], options["block"], rng)
    assert rng.getstate() == state


def test_block_bootstrap_preserves_valid_draws_and_oversized_block_clamping() -> None:
    residuals = [1.0, -2.0, 3.0]
    for length, block in ((1, 1), (7, 2), (3, 9)):
        first = block_bootstrap(residuals, length, block, random.Random(34))
        again = block_bootstrap(residuals, length, block, random.Random(34))
        assert first == again
        assert len(first) == length
        assert set(first) <= set(residuals)
    assert block_bootstrap(residuals, 3, 9, random.Random(34)) == tuple(residuals)


def test_block_bootstrap_keeps_missing_errors_error_precedence() -> None:
    with pytest.raises(ValueError, match="at least one error"):
        block_bootstrap([], 0, 0, random.Random(34))
