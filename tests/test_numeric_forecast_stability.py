"""Finite RMSE and safety stock must survive floating-point squaring limits."""

from __future__ import annotations

import math

import pytest

from inventory_policy_lab import backtest, naive, safety_stock


def test_backtest_rmse_remains_finite_when_squaring_the_error_would_overflow() -> None:
    result = backtest([1e200, 1e200, 1e200, 0.0], "naive", naive, holdout=1)
    assert math.isfinite(result.rmse)
    assert result.rmse == pytest.approx(1e200)
    assert result.mae == pytest.approx(1e200)
    assert result.bias == pytest.approx(1e200)
    assert result.mase is None


def test_backtest_rmse_with_large_opposite_errors_has_correct_magnitude() -> None:
    # Naive forecasts 0 then 1e200, versus actual demand 1e200 then 0.
    result = backtest([0.0, 0.0, 0.0, 1e200, 0.0], "naive", naive, holdout=2)
    assert result.forecasts == (0.0, 1e200)
    assert result.rmse == pytest.approx(1e200)
    assert result.mae == pytest.approx(1e200)
    assert result.bias == pytest.approx(0.0)


def test_backtest_rmse_does_not_underflow_small_nonzero_errors_to_zero() -> None:
    result = backtest([1e-200, 1e-200, 1e-200, 0.0], "naive", naive, holdout=1)
    assert result.rmse == pytest.approx(1e-200, rel=1e-12, abs=0)
    assert result.rmse > 0


def test_backtest_rmse_zero_and_ordinary_errors_remain_consistent() -> None:
    perfect = backtest([4, 4, 4, 4], "naive", naive, holdout=1)
    assert perfect.rmse == 0
    errors = backtest([5, 5, 5, 2, 6], "naive", naive, holdout=2)
    # Errors +3 and -4: RMSE sqrt((3² + 4²) / 2).
    assert errors.rmse == pytest.approx(math.sqrt(12.5))


def test_safety_stock_stays_finite_when_intermediate_variance_overflows() -> None:
    z, stock = safety_stock(0.95, demand_per_period=0, sigma_demand=1e200, lead_time=1)
    assert stock == pytest.approx(z * 1e200)
    assert math.isfinite(stock)

    z, stock = safety_stock(
        0.95,
        demand_per_period=1e200,
        sigma_demand=1e200,
        lead_time=1,
        sigma_lead_time=1,
    )
    assert stock == pytest.approx(z * math.sqrt(2) * 1e200)
    assert math.isfinite(stock)


def test_safety_stock_stays_finite_when_intermediate_variance_underflows() -> None:
    z, stock = safety_stock(0.95, demand_per_period=0, sigma_demand=1e-200, lead_time=1)
    assert stock == pytest.approx(z * 1e-200, rel=1e-12, abs=0)
    assert stock > 0
