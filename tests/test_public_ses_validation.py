"""The standalone SES API must reject impossible demand observations."""

from __future__ import annotations

import math

import pytest

from inventory_policy_lab import ses


@pytest.mark.parametrize("invalid", [-1.0, -0.01, math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("position", [0, 2])
def test_ses_rejects_invalid_demand(invalid: float, position: int) -> None:
    values = [3.0, 0.0, 5.0]
    values[position] = invalid
    with pytest.raises(ValueError, match=rf"demand\[{position}\] must be finite and non-negative"):
        ses(values)


def test_ses_rejects_empty_demand_with_actionable_error() -> None:
    with pytest.raises(ValueError, match="at least one observed demand period"):
        ses([])


def test_ses_keeps_valid_zero_and_positive_demand() -> None:
    assert ses([0.0, 0.0, 0.0]) == 0.0
    assert ses([10.0, 20.0, 0.0], alpha=0.5) == pytest.approx(7.5)


def test_ses_keeps_large_finite_demand_supported() -> None:
    assert ses([1e308, 0.0, 1e308], alpha=0.5) == pytest.approx(7.5e307)
