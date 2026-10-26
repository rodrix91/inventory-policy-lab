"""Ensure direct forecasting API calls use the same valid settings as Config."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import pytest

from inventory_policy_lab import Config, ConfigError, croston, moving_average, sba, ses


@pytest.mark.parametrize("window", [0, -1, -100])
def test_direct_moving_average_rejects_nonpositive_windows(window: int) -> None:
    # In particular, Python slicing with [-0:] would silently use all observations.
    with pytest.raises(ValueError, match="moving-average window must be at least 1"):
        moving_average([1, 2, 10], window=window)


@pytest.mark.parametrize("alpha", [0.0, -0.1, 1.01, math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("method", [ses, croston, sba])
def test_direct_smoothing_rejects_invalid_alpha(
    method: Callable[[Sequence[float], float], float], alpha: float
) -> None:
    with pytest.raises(ValueError, match="alpha must be in"):
        method([0, 5, 0, 10], alpha)


def test_direct_forecasts_preserve_valid_boundary_and_short_history_results() -> None:
    assert moving_average([1, 2, 10], window=1) == 10
    assert moving_average([1, 2, 10], window=99) == pytest.approx(13 / 3)
    assert ses([2, 8, 4], alpha=1.0) == 4
    assert ses([2, 8, 4], alpha=0.5) == pytest.approx(4.5)
    assert croston([0, 0, 8, 0], alpha=1.0) == pytest.approx(8 / 3)
    assert sba([0, 0, 8, 0], alpha=1.0) == pytest.approx(4 / 3)
    assert croston([0, 0, 0], alpha=0.1) == 0
    assert sba([0, 0, 0], alpha=0.1) == 0


def test_same_smoothing_guards_apply_even_to_zero_demand() -> None:
    with pytest.raises(ValueError, match="croston alpha"):
        croston([0, 0, 0], alpha=math.nan)
    with pytest.raises(ValueError, match="croston alpha"):
        sba([0, 0, 0], alpha=math.inf)


def test_direct_api_thresholds_match_config_validation() -> None:
    Config(ma_window=1, ses_alpha=1, croston_alpha=1).validate()
    with pytest.raises(ConfigError, match="moving-average window"):
        Config(ma_window=0).validate()
    with pytest.raises(ConfigError, match="ses alpha"):
        Config(ses_alpha=0).validate()
    with pytest.raises(ConfigError, match="croston alpha"):
        Config(croston_alpha=1.5).validate()
