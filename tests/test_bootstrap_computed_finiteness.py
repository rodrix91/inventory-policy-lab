"""Computed bootstrap quantities must not hide binary64 overflow."""

from __future__ import annotations

import math
import random

import pytest

from inventory_policy_lab import bootstrap_safety_stock
from inventory_policy_lab.errors import DataError


def test_expected_interval_overflow_fails_before_random_draws() -> None:
    # With all-zero historical demand, an infinite expected quantity would
    # otherwise be subtracted from the zero quantile, yielding a false 0 stock.
    rng = random.Random(41)
    prior = rng.getstate()
    with pytest.raises(DataError, match="expected interval demand exceeds"):
        bootstrap_safety_stock([0.0], 0.95, 1e308, lead_time=2.0, samples=10, rng=rng)
    assert rng.getstate() == prior


def test_overflowed_protection_duration_fails_even_with_zero_forecast() -> None:
    rng = random.Random(5)
    prior = rng.getstate()
    with pytest.raises(DataError, match="expected interval demand exceeds"):
        bootstrap_safety_stock(
            [0.0],
            0.95,
            0.0,
            lead_time=1e308,
            review_period=1e308,
            lead_times=(0.0,),
            samples=3,
            rng=rng,
        )
    assert rng.getstate() == prior


def test_overflowed_sample_sum_raises_domain_error_not_raw_overflow() -> None:
    # fsum([1e308, 1e308]) raises OverflowError despite finite source rows.
    with pytest.raises(DataError, match="sampled interval demand exceeds"):
        bootstrap_safety_stock(
            [1e308],
            0.95,
            0.0,
            lead_time=2.0,
            samples=1,
            rng=random.Random(9),
        )


def test_large_representable_bootstrap_results_remain_supported() -> None:
    quantile, stock = bootstrap_safety_stock(
        [1e307],
        0.95,
        1e307,
        lead_time=2.0,
        samples=4,
        rng=random.Random(9),
    )
    assert math.isfinite(quantile)
    assert quantile == pytest.approx(2e307)
    assert stock == 0.0


def test_ordinary_bootstrap_quantile_and_stock_are_unchanged() -> None:
    quantile, stock = bootstrap_safety_stock(
        [2.0],
        0.95,
        1.5,
        lead_time=2.0,
        samples=4,
        rng=random.Random(9),
    )
    assert (quantile, stock) == (4.0, 1.0)
