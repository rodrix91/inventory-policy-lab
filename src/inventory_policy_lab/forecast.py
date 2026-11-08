"""One-step-ahead forecasting methods and a holdout backtest.

Every method takes the history observed so far and returns the forecast of
demand per period for the next period. The backtest re-runs the method at each
holdout period with only the data before it (rolling origin, one step ahead).
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from numbers import Real

from .errors import DataError

Method = Callable[[Sequence[float]], float]


def _stable_fmean(values: Sequence[float]) -> float:
    """Mean of finite values without overflowing an intermediate sum.

    An ordinary mean uses the standard library's accurate fmean. If its
    intermediate sum overflows although the mean is representable, normalize
    by the largest magnitude before averaging and restoring the scale.
    """
    try:
        return statistics.fmean(values)
    except OverflowError:
        scale = max(abs(value) for value in values)
        return statistics.fmean(value / scale for value in values) * scale


def _valid_demand_value(value: float) -> bool:
    """Accept non-negative finite demand, not booleans or malformed Python inputs."""
    # math.isfinite() accepts Decimal via float conversion, but smoothing
    # coefficients are floats and mixed Decimal arithmetic then raises
    # TypeError. Accept real-number values with compatible float arithmetic.
    if isinstance(value, bool) or not isinstance(value, Real):
        return False
    try:
        return math.isfinite(value) and value >= 0
    except (TypeError, ValueError, OverflowError):
        return False


def _validate_demand(history: Sequence[float], method: str) -> None:
    """Reject invalid demand anywhere in a history, even outside a forecast window."""
    if not history:
        raise ValueError(f"{method} needs at least one observed demand period")
    for index, value in enumerate(history):
        if not _valid_demand_value(value):
            raise ValueError(f"demand[{index}] must be finite and non-negative")


def naive(history: Sequence[float]) -> float:
    """The last observed demand, requiring a finite, non-negative history."""
    _validate_demand(history, "naive")
    return history[-1]


def moving_average(history: Sequence[float], window: int = 3) -> float:
    """Mean of the last ``window`` periods (fewer when the history is shorter).

    Require a positive integer window even for standalone callers.
    Python's ``[-0:]`` slice would otherwise silently average every period,
    and booleans are integers in Python but are not meaningful window sizes.
    """
    if isinstance(window, bool) or not isinstance(window, int):
        raise ValueError(f"moving-average window must be a positive integer, got {window!r}")
    if window < 1:
        raise ValueError(f"moving-average window must be at least 1, got {window}")
    _validate_demand(history, "moving-average")
    return _stable_fmean(history[-window:])


def _validate_alpha(alpha: float, method: str) -> None:
    """Require a real numeric smoothing weight, never a boolean or string."""
    if isinstance(alpha, bool) or not isinstance(alpha, (int, float)) or not 0 < alpha <= 1:
        raise ValueError(f"{method} alpha must be in (0, 1], got {alpha}")


def ses(history: Sequence[float], alpha: float = 0.2) -> float:
    """Simple exponential smoothing for finite, non-negative demand.

    Direct library callers get an actionable error on invalid demand rather
    than a NaN/infinite forecast or an accidental negative stock estimate.
    """
    _validate_alpha(alpha, "ses")
    _validate_demand(history, "ses")
    level = history[0]
    for value in history[1:]:
        level += alpha * (value - level)
    return level


def _croston_parts(history: Sequence[float], alpha: float) -> tuple[float, float] | None:
    """Smoothed demand size and inter-demand interval, or ``None`` without demand.

    Both start at the first demand: the size at its value, the interval at the
    number of periods up to and including it. They are updated only in periods
    with demand, the interval with the periods since the previous demand.
    """
    size = interval = 0.0
    last = -1
    for index, value in enumerate(history):
        # Direct library callers must not silently interpret negative demand
        # as a zero period or propagate NaN/infinity into a forecast.
        if not _valid_demand_value(value):
            raise ValueError(f"demand[{index}] must be finite and non-negative")
        if value == 0:
            continue
        gap = index - last
        if last < 0:
            size, interval = value, float(gap)
        else:
            size += alpha * (value - size)
            interval += alpha * (gap - interval)
        last = index
    if last < 0:
        return None
    return size, interval


def croston(history: Sequence[float], alpha: float = 0.1) -> float:
    """Croston (1972): smoothed size divided by smoothed interval; 0 without demand."""
    _validate_alpha(alpha, "croston")
    parts = _croston_parts(history, alpha)
    return 0.0 if parts is None else parts[0] / parts[1]


def sba(history: Sequence[float], alpha: float = 0.1) -> float:
    """Syntetos-Boylan approximation: Croston times ``1 - alpha / 2`` (bias correction)."""
    _validate_alpha(alpha, "sba")
    return (1 - alpha / 2) * croston(history, alpha)


@dataclass(frozen=True)
class BacktestResult:
    """Accuracy of one method over the holdout periods."""

    method: str
    forecasts: tuple[float, ...]
    mae: float
    rmse: float
    bias: float  # mean of forecast - actual: positive means over-forecasting
    mase: float | None  # None when the in-sample naive error is zero


def naive_scale(train: Sequence[float]) -> float:
    """Mean absolute one-step naive error in the training data (MASE denominator).

    Standalone callers must provide two or more valid demand observations.
    A missing or corrupted baseline cannot reliably scale forecast errors.
    """
    if len(train) < 2:
        raise ValueError("naive_scale requires at least two observed demand periods")
    _validate_demand(train, "naive_scale")
    return _stable_fmean([abs(train[i] - train[i - 1]) for i in range(1, len(train))])


def backtest(series: Sequence[float], name: str, method: Method, holdout: int) -> BacktestResult:
    """Score ``method`` on the last ``holdout`` periods of ``series``.

    MASE follows Hyndman & Koehler (2006): MAE over the holdout divided by the
    in-sample MAE of the one-step naive forecast on the training periods. It is
    defined on series with zeros, unlike MAPE. Needs ``holdout >= 1`` and at
    least two training periods. Demand and forecasts must be finite and
    non-negative; errors identify the original zero-based series period.
    """
    if isinstance(holdout, bool) or not isinstance(holdout, int):
        raise ValueError("backtest holdout must be a positive integer")
    start = len(series) - holdout
    if holdout < 1 or start < 2:
        raise ValueError("backtest needs holdout >= 1 and at least 2 training periods")
    # Validate the entire series, including holdout actuals which never enter
    # the first forecast's history. Otherwise NaN may contaminate MAE/MASE.
    _validate_demand(series, "backtest")
    forecasts = []
    for t in range(start, len(series)):
        forecast = method(series[:t])
        # Apply the same numeric contract as observed demand. math.isfinite()
        # alone accepts Decimal values, which then raise TypeError when
        # subtracted from the float actuals during accuracy calculations.
        if not _valid_demand_value(forecast):
            raise ValueError(f"{name} forecast[{t}] must be finite and non-negative")
        forecasts.append(forecast)
    errors = [f - a for f, a in zip(forecasts, series[start:], strict=True)]
    mae = _stable_fmean([abs(e) for e in errors])
    # Squaring a finite error can overflow, even when its RMSE is finite.
    # Normalize first, then restore the scale after taking the square root.
    # This also keeps the public RMSE and --sigma rmse finite for large units.
    maximum_error = max(abs(e) for e in errors)
    rmse = (
        maximum_error * math.sqrt(math.fsum((e / maximum_error) ** 2 for e in errors) / len(errors))
        if maximum_error
        else 0.0
    )
    scale = naive_scale(series[:start])
    mase = mae / scale if scale > 0 else None
    # A tiny but nonzero training scale and a very large holdout error can
    # overflow the ratio even though every demand value and error is finite.
    # Reporting Infinity would corrupt standard JSON and model comparisons.
    if mase is not None and not math.isfinite(mase):
        raise DataError(f"{name} MASE exceeds the finite numeric range")
    return BacktestResult(
        method=name,
        forecasts=tuple(forecasts),
        mae=mae,
        rmse=rmse,
        bias=_stable_fmean(errors),
        mase=mase,
    )


def pick_best(results: Sequence[BacktestResult]) -> BacktestResult:
    """Lowest MASE; by MAE when MASE is undefined; ties go to the earlier method."""
    if not results:
        raise ValueError("pick_best requires at least one backtest result")
    if all(r.mase is not None for r in results):
        return min(results, key=lambda r: r.mase if r.mase is not None else math.inf)
    return min(results, key=lambda r: r.mae)
