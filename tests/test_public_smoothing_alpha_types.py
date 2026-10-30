"""Public SES, Croston and SBA must reject malformed smoothing coefficients."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import pytest

from inventory_policy_lab import croston, sba, ses


@pytest.mark.parametrize("method", [ses, croston, sba])
@pytest.mark.parametrize(
    "invalid",
    [True, False, "0.5", None, 1 + 2j, object(), [0.5], {"alpha": 0.5}],
)
def test_smoothing_rejects_invalid_alpha_types_before_demand(
    method: Callable[[Sequence[float], float], float], invalid: Any
) -> None:
    # An invalid alpha must fail before this corrupt demand is processed.
    message = "ses alpha must be in" if method is ses else "croston alpha must be in"
    with pytest.raises(ValueError, match=message):
        method([-1.0, float("nan")], invalid)


def test_valid_integer_alpha_one_retains_forecasts() -> None:
    assert ses([2.0, 8.0, 4.0], alpha=1) == 4.0
    assert croston([0.0, 0.0, 8.0, 0.0], alpha=1) == pytest.approx(8 / 3)
    assert sba([0.0, 0.0, 8.0, 0.0], alpha=1) == pytest.approx(4 / 3)
