"""Public Holt-Winters APIs validate calendar season counts before fitting.

The low-level fit and the grid-based fit are both exposed by the package.
Non-integer season lengths previously reached float slices or comparisons,
raising TypeError instead of an actionable input error.
"""

from __future__ import annotations

import math
from typing import Any, cast

import pytest

from inventory_policy_lab import fit_holt_winters, holt_winters, holt_winters_fit


_HISTORY = (10.0, 20.0, 12.0, 24.0, 11.0, 22.0)


def _call_model(method: str, season_length: int) -> None:
    if method == "direct":
        holt_winters_fit(
            _HISTORY, season_length, alpha=0.5, beta=0.5, gamma=0.5, phi=0.9
        )
    elif method == "grid":
        fit_holt_winters(_HISTORY, season_length)
    else:
        holt_winters(_HISTORY, season_length)


@pytest.mark.parametrize("method", ["direct", "grid", "forecast"])
@pytest.mark.parametrize(
    "invalid",
    [True, False, 2.0, 2.5, "2", None, math.nan, math.inf, -math.inf, 1 + 0j, [], {}, object()],
)
def test_holt_winters_public_methods_reject_noninteger_seasons(
    method: str, invalid: Any
) -> None:
    with pytest.raises(ValueError, match="season_length must be an integer"):
        _call_model(method, cast(int, invalid))


@pytest.mark.parametrize("method", ["direct", "grid", "forecast"])
@pytest.mark.parametrize("invalid", [-2, 0, 1])
def test_integer_seasons_shorter_than_two_keep_existing_diagnostic(
    method: str, invalid: int
) -> None:
    with pytest.raises(ValueError, match="Holt-Winters needs a season length >= 2"):
        _call_model(method, invalid)


def test_valid_integer_season_preserves_direct_and_grid_forecasts() -> None:
    direct = holt_winters_fit(
        _HISTORY, 2, alpha=0.5, beta=0.5, gamma=0.5, phi=0.9
    )
    grid = fit_holt_winters(_HISTORY, 2)
    assert math.isfinite(direct.forecast(1))
    assert grid.model == "hw_additive"
    assert holt_winters(_HISTORY, 2) == pytest.approx(grid.forecast(1))
