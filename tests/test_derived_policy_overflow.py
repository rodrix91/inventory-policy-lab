"""Derived dynamic stock quantities must remain finite for public API users."""

from __future__ import annotations

import math

import pytest

from inventory_policy_lab import DataError, dynamic_levels, period_safety_stocks


def test_dynamic_levels_reject_multiplication_overflow() -> None:
    with pytest.raises(DataError, match="dynamic inventory levels exceed"):
        dynamic_levels([0.0, 1e308, 1e308], 1, 2.0, 0.0, 0.0)


def test_dynamic_levels_reject_overflow_from_adding_safety_stock() -> None:
    with pytest.raises(DataError, match="dynamic inventory levels exceed"):
        dynamic_levels([0.0, 1e308], 1, 1.0, 0.0, 1e308)


def test_period_safety_stocks_reject_derived_overflow() -> None:
    with pytest.raises(DataError, match="period safety stock exceeds"):
        period_safety_stocks([0.0, 1e308], 1, 1.0, 0.0, 2.0)


def test_large_representable_derived_quantities_are_preserved() -> None:
    levels = dynamic_levels([0.0, 1e307, 1e307], 1, 2.0, 0.0, 1e307)
    stocks = period_safety_stocks([0.0, 1e307, 1e307], 1, 2.0, 0.0, 0.5)
    assert all(math.isfinite(value) for value in (*levels, *stocks))
    assert levels == pytest.approx((3e307,))
    assert stocks == pytest.approx((1e307,))


def test_ordinary_dynamic_levels_and_zero_relative_error_are_unchanged() -> None:
    assert dynamic_levels([0.0, 10.0, 20.0], 1, 2.0, 0.0, 3.0) == (33.0,)
    assert period_safety_stocks([0.0, 10.0, 20.0], 1, 2.0, 0.0, -0.5) == (0.0,)
