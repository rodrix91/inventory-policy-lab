"""Forecasting APIs reject malformed demand values with indexed, actionable errors.

This guards direct Python callers, which may bypass the CSV reader and Config.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Any, cast

import pytest

from inventory_policy_lab import backtest, croston, moving_average, naive, sba, ses


@pytest.mark.parametrize(
    "invalid",
    [True, False, "3", None, 1 + 0j, object(), 10**400, Decimal("2.5")],
    ids=["true", "false", "numeric-string", "none", "complex", "object", "huge-int", "decimal"],
)
@pytest.mark.parametrize("position", [0, 2])
@pytest.mark.parametrize("method", [naive, moving_average, ses, croston, sba])
def test_forecasts_reject_malformed_demand_at_original_index(
    method: Callable[[Sequence[float]], float], position: int, invalid: Any
) -> None:
    history = [2.0, 0.0, 5.0]
    history[position] = cast(float, invalid)
    with pytest.raises(ValueError, match=rf"demand\[{position}\] must be finite and non-negative"):
        method(history)


@pytest.mark.parametrize(
    "invalid",
    [True, False, "3", None, 1 + 0j, object(), 10**400, Decimal("2.5")],
    ids=["true", "false", "numeric-string", "none", "complex", "object", "huge-int", "decimal"],
)
@pytest.mark.parametrize("position", [0, 2, 4])
def test_backtest_rejects_malformed_actuals_before_invoking_model(
    position: int, invalid: Any
) -> None:
    history = [2.0, 3.0, 4.0, 5.0, 6.0]
    history[position] = cast(float, invalid)
    calls: list[int] = []

    def model(observed: Sequence[float]) -> float:
        calls.append(len(observed))
        return 2.0

    with pytest.raises(ValueError, match=rf"demand\[{position}\] must be finite and non-negative"):
        backtest(history, "constant", model, holdout=2)
    assert calls == []


def test_regular_integer_float_and_zero_demand_still_work() -> None:
    history = [0, 2.0, 4]
    assert naive(history) == 4
    assert moving_average(history, window=2) == 3.0
    assert ses(history, alpha=1.0) == 4.0
    assert math.isfinite(croston(history))
    assert math.isfinite(sba(history))
    assert backtest([0, 2, 4, 6], "naive", naive, holdout=1).forecasts == (4,)
