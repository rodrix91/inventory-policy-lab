"""Exponential smoothing with trend and seasonality: damped Holt and Holt-Winters.

Both models are fitted to the history they are given and nothing else. The
smoothing parameters are chosen by a grid search that minimises the sum of
squared one-step errors inside that history, so when the backtest calls a
method at each holdout origin, or the out-of-sample replay fits on the training
periods, the later periods cannot influence the fit (ADR 0006).

Damped Holt (Gardner & McKenzie, 1985), with ``0 < phi < 1``::

    F(t+h) = L(t) + (phi + phi^2 + ... + phi^h) B(t)
    L(t)   = a y(t) + (1 - a) (L(t-1) + phi B(t-1))
    B(t)   = b (L(t) - L(t-1)) + (1 - b) phi B(t-1)
    start: L(2) = y(2), B(2) = y(2) - y(1)

Holt-Winters with a damped trend and a season of ``m`` periods (Winters, 1960),
additive (``+ S``) or multiplicative (``x S``)::

    F(t+h) = (L(t) + (phi + ... + phi^h) B(t)) + S(t+h-m)     (additive)
    L(t)   = a (y(t) - S(t-m)) + (1 - a) (L(t-1) + phi B(t-1))
    B(t)   = b (L(t) - L(t-1)) + (1 - b) phi B(t-1)
    S(t)   = g (y(t) - L(t)) + (1 - g) S(t-m)
    start (needs two full seasons): L(m) = mean of season 1,
    B(m) = (mean of season 2 - mean of season 1) / m, S(i) = y(i) - L(m)

The multiplicative form divides by ``S`` and ``L`` instead of subtracting them
and starts with ``S(i) = y(i) / L(m)``; it needs demand above zero in every
period. Forecasts are floored at zero, because demand cannot be negative.

A grid fit depends only on the history it is given, and the backtest, the
residual errors and every rolling origin refit the same prefixes of a series
again and again. :func:`fit_holt_damped` and :func:`fit_holt_winters` therefore
keep the fits of recent histories in a bounded cache keyed on the exact values
(their types and ``repr``, so ``10`` and ``10.0`` or ``0.0`` and ``-0.0`` are
different keys) and return the stored :class:`SmoothingFit`, which is frozen.
A history with no valid fit is cached as that :class:`FitError` message. The
results are the same as without the cache, bit for bit (ADR 0010).
"""

from __future__ import annotations

import math
import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass
from functools import partial
from itertools import product
from typing import Union

# Grids of the parameter search. Phi stays below 1 on purpose: an undamped
# trend extrapolated over a lead time is the classic way to overshoot, and the
# damped trend is the more robust default (Gardner & McKenzie, 1985).
ALPHAS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
BETAS = (0.05, 0.1, 0.2, 0.3)
GAMMAS = (0.05, 0.1, 0.2, 0.3)
PHIS = (0.8, 0.9, 0.95, 0.98)

HOLT_MIN_HISTORY = 4  # two points to start, at least two one-step errors to score
SEASONAL_KINDS = ("additive", "multiplicative")


class FitError(ValueError):
    """No parameter set in the grid gives a valid fit (multiplicative level not positive)."""


FIT_CACHE_SIZE = 4096  # grid fits kept, least recently used dropped first

_Entry = Union["SmoothingFit", str]  # a fit, or the FitError message of a history with none


@dataclass(frozen=True)
class FitCacheInfo:
    """Counters of the fit cache: requests answered from it, requests that ran a grid."""

    hits: int
    misses: int
    size: int
    max_size: int


class _FitCache:
    """A bounded, thread-safe LRU store of grid fits keyed on the exact history."""

    def __init__(self, max_size: int) -> None:
        self.max_size = max_size
        self._data: OrderedDict[Hashable, _Entry] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: Hashable) -> _Entry | None:
        """The stored entry of a requested history, counted as a hit or a miss."""
        with self._lock:
            found = self._data.get(key)
            if found is None:
                self.misses += 1
            else:
                self._data.move_to_end(key)
                self.hits += 1
            return found

    def __contains__(self, key: Hashable) -> bool:
        with self._lock:
            return key in self._data

    def put(self, entries: Sequence[tuple[Hashable, _Entry]]) -> None:
        """Store ``entries`` in order (the last one is the most recently used)."""
        with self._lock:
            for key, entry in entries:
                self._data[key] = entry
                self._data.move_to_end(key)
            while len(self._data) > self.max_size:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self.hits = self.misses = 0

    def info(self) -> FitCacheInfo:
        with self._lock:
            return FitCacheInfo(self.hits, self.misses, len(self._data), self.max_size)


_CACHE = _FitCache(FIT_CACHE_SIZE)


def _history_key(history: Sequence[float]) -> tuple[frozenset[type], str]:
    """Exact identity of a history: the value types and the ``repr`` of every value."""
    values = tuple(history)
    return frozenset(map(type, values)), repr(values)


def fit_cache_info() -> FitCacheInfo:
    """Hits, misses and size of the cache behind :func:`fit_holt_damped` and
    :func:`fit_holt_winters`."""
    return _CACHE.info()


def clear_fit_cache() -> None:
    """Empty the fit cache and reset its counters."""
    _CACHE.clear()


@dataclass(frozen=True)
class SmoothingFit:
    """A fitted model: final states, the parameters picked and the in-sample SSE."""

    model: str  # "holt_damped", "hw_additive" or "hw_multiplicative"
    alpha: float
    beta: float
    phi: float
    gamma: float | None  # None for damped Holt
    level: float
    trend: float
    seasonals: tuple[float, ...]  # factor of the next period first; empty for Holt
    sse: float  # sum of squared one-step errors inside the history

    def forecast(self, horizon: int = 1) -> float:
        """Forecast ``horizon`` periods after the end of the history, floored at zero."""
        if horizon < 1:
            raise ValueError(f"horizon must be at least 1, got {horizon}")
        damping = sum(self.phi**i for i in range(1, horizon + 1))
        base = self.level + damping * self.trend
        if self.seasonals:
            season = self.seasonals[(horizon - 1) % len(self.seasonals)]
            base = base * season if self.model == "hw_multiplicative" else base + season
        return max(base, 0.0)

    def mean_forecast(self, horizon: int) -> float:
        """Mean of the forecasts for 1 to ``horizon`` periods ahead (at least one)."""
        steps = max(horizon, 1)
        return math.fsum(self.forecast(h) for h in range(1, steps + 1)) / steps

    def calendar_forecasts(self, fitted_periods: int, periods: int) -> tuple[float, ...]:
        """Forecast of each period ``0 .. periods - 1`` of a calendar the fit started at.

        The fit saw periods ``0 .. fitted_periods - 1``. A later period ``i`` gets
        the real forecast ``i - fitted_periods + 1`` steps ahead. An earlier one,
        replayed in-sample, gets the forecast of the next period in the same
        season position (``1`` to ``m`` steps ahead; ``1`` step for damped Holt):
        the seasonal profile at the final level and trend, the same way the
        in-sample replay of a static policy applies the final level to the
        whole history (ADR 0007).
        """
        season = len(self.seasonals) or 1
        values = []
        for i in range(periods):
            horizon = i - fitted_periods + 1
            if horizon < 1:
                horizon = (horizon - 1) % season + 1
            values.append(self.forecast(horizon))
        return tuple(values)

    def parameters(self) -> dict[str, float]:
        values = {"alpha": self.alpha, "beta": self.beta, "phi": self.phi}
        if self.gamma is not None:
            values["gamma"] = self.gamma
        return values


def holt_damped_fit(
    history: Sequence[float], alpha: float, beta: float, phi: float
) -> SmoothingFit:
    """Damped Holt with the given parameters (needs at least two periods)."""
    if len(history) < 2:
        raise ValueError("damped Holt needs at least 2 periods")
    level, trend = history[1], history[1] - history[0]
    sse = 0.0
    for value in history[2:]:
        expected = level + phi * trend
        sse += (value - expected) ** 2
        new_level = alpha * value + (1 - alpha) * expected
        trend = beta * (new_level - level) + (1 - beta) * phi * trend
        level = new_level
    return SmoothingFit("holt_damped", alpha, beta, phi, None, level, trend, (), sse)


def holt_winters_fit(
    history: Sequence[float],
    season_length: int,
    alpha: float,
    beta: float,
    gamma: float,
    phi: float,
    seasonal: str = "additive",
) -> SmoothingFit:
    """Holt-Winters with the given parameters (needs two full seasons).

    Raises :class:`FitError` when the multiplicative level stops being positive.
    """
    if seasonal not in SEASONAL_KINDS:
        raise ValueError(f"seasonal must be 'additive' or 'multiplicative', got {seasonal!r}")
    m = season_length
    if m < 2 or len(history) < 2 * m:
        raise ValueError("Holt-Winters needs a season length >= 2 and two full seasons")
    multiplicative = seasonal == "multiplicative"
    first = math.fsum(history[:m]) / m
    second = math.fsum(history[m : 2 * m]) / m
    level, trend = first, (second - first) / m
    if multiplicative:
        if min(history) <= 0:
            raise FitError("multiplicative Holt-Winters needs demand above zero in every period")
        seasonals = [value / level for value in history[:m]]
    else:
        seasonals = [value - level for value in history[:m]]
    sse = 0.0
    for value in history[m:]:
        old = seasonals.pop(0)
        base = level + phi * trend
        if multiplicative:
            sse += (value - base * old) ** 2
            new_level = alpha * value / old + (1 - alpha) * base
            if new_level <= 0:
                raise FitError("multiplicative Holt-Winters level fell to zero or below")
            seasonals.append(gamma * value / new_level + (1 - gamma) * old)
        else:
            sse += (value - base - old) ** 2
            new_level = alpha * (value - old) + (1 - alpha) * base
            seasonals.append(gamma * (value - new_level) + (1 - gamma) * old)
        trend = beta * (new_level - level) + (1 - beta) * phi * trend
        level = new_level
    model = "hw_multiplicative" if multiplicative else "hw_additive"
    return SmoothingFit(model, alpha, beta, phi, gamma, level, trend, tuple(seasonals), sse)


def _cached_grid(
    tag: tuple[Hashable, ...],
    history: Sequence[float],
    shortest: int,
    grid: Callable[[tuple[float, ...], list[int]], dict[int, _Entry]],
) -> SmoothingFit:
    """The grid fit of ``history``, from the cache or from one pass over every prefix.

    On a miss, ``grid`` scores every parameter set once over the whole history,
    which gives the SSE of every prefix of at least ``shortest`` periods at the
    cost of a single fit, and returns the best fit of each prefix not cached yet;
    all of them are stored, because the backtest and the rolling origins ask for
    those prefixes next.
    """
    values = tuple(history)
    found = _CACHE.get((*tag, _history_key(values)))
    if found is None:
        keys = {k: (*tag, _history_key(values[:k])) for k in range(shortest, len(values) + 1)}
        wanted = [k for k, key in keys.items() if k == len(values) or key not in _CACHE]
        computed = grid(values, wanted)
        _CACHE.put([(keys[k], computed[k]) for k in wanted])
        found = computed[len(values)]
    if isinstance(found, str):
        raise FitError(found)
    return found


def _best_by_prefix(
    rows: Sequence[tuple[tuple[float, ...], Sequence[float]]], wanted: Sequence[int], offset: int
) -> dict[int, tuple[float, ...] | None]:
    """For each prefix length in ``wanted``, the first parameter set of lowest SSE.

    ``rows`` holds, in grid order, each parameter set and the SSE after each
    step, the step that ends a prefix of ``k`` periods at index ``k - offset``
    (shorter when the set became invalid). Strictly lower wins, as in a plain
    grid search, so ties keep the first set.
    """
    best: dict[int, tuple[float, ...] | None] = {}
    for k in wanted:
        index = k - offset
        params: tuple[float, ...] | None = None
        lowest = 0.0
        for candidate, sses in rows:
            if index < len(sses) and (params is None or sses[index] < lowest):
                params, lowest = candidate, sses[index]
        best[k] = params
    return best


def fit_holt_damped(history: Sequence[float]) -> SmoothingFit:
    """Damped Holt with the grid parameters of lowest in-sample SSE (first on ties)."""
    if len(history) < HOLT_MIN_HISTORY:
        raise ValueError(f"damped Holt is fitted on at least {HOLT_MIN_HISTORY} periods")
    return _cached_grid(("holt_damped",), history, HOLT_MIN_HISTORY, _grid_holt_damped)


def _grid_holt_damped(values: tuple[float, ...], wanted: list[int]) -> dict[int, _Entry]:
    """Best damped Holt fit of each prefix length in ``wanted``, from one pass per set.

    The SSE recursion is the one of :func:`holt_damped_fit`, step for step, so
    the SSE of a prefix is the same float a fit on that prefix computes.
    """
    rows = []
    for alpha, beta, phi in product(ALPHAS, BETAS, PHIS):
        level, trend = values[1], values[1] - values[0]
        sse = 0.0
        sses = []
        for value in values[2:]:
            expected = level + phi * trend
            sse += (value - expected) ** 2
            new_level = alpha * value + (1 - alpha) * expected
            trend = beta * (new_level - level) + (1 - beta) * phi * trend
            level = new_level
            sses.append(sse)
        rows.append(((alpha, beta, phi), sses))
    out: dict[int, _Entry] = {}
    for k, params in _best_by_prefix(rows, wanted, 3).items():
        assert params is not None  # damped Holt has no invalid parameter set
        out[k] = holt_damped_fit(values[:k], *params)
    return out


def fit_holt_winters(
    history: Sequence[float], season_length: int, seasonal: str = "additive"
) -> SmoothingFit:
    """Holt-Winters with the grid parameters of lowest in-sample SSE (first on ties).

    Parameter sets whose multiplicative level is not positive are skipped; when
    none is left (or the history has a zero), :class:`FitError` is raised.
    """
    if seasonal == "multiplicative" and min(history, default=0) <= 0:
        raise FitError("multiplicative Holt-Winters needs demand above zero in every period")
    if seasonal not in SEASONAL_KINDS:
        raise ValueError(f"seasonal must be 'additive' or 'multiplicative', got {seasonal!r}")
    if season_length < 2 or len(history) < 2 * season_length:
        raise ValueError("Holt-Winters needs a season length >= 2 and two full seasons")
    return _cached_grid(
        ("holt_winters", season_length, seasonal),
        history,
        2 * season_length,
        partial(_grid_holt_winters, m=season_length, seasonal=seasonal),
    )


def _grid_holt_winters(
    values: tuple[float, ...], wanted: list[int], m: int, seasonal: str
) -> dict[int, _Entry]:
    """Best Holt-Winters fit of each prefix length in ``wanted``, from one pass per set.

    The start uses the first two seasons only, so it is the same for every
    prefix, and the recursion is the one of :func:`holt_winters_fit`, step for
    step. A multiplicative set whose level stops being positive at a step is
    invalid for the prefixes that include that step and valid for the shorter ones.
    """
    multiplicative = seasonal == "multiplicative"
    first = math.fsum(values[:m]) / m
    second = math.fsum(values[m : 2 * m]) / m
    start_level, start_trend = first, (second - first) / m
    if multiplicative:
        start_seasonals = [value / start_level for value in values[:m]]
    else:
        start_seasonals = [value - start_level for value in values[:m]]
    rows = []
    for alpha, beta, gamma, phi in product(ALPHAS, BETAS, GAMMAS, PHIS):
        level, trend = start_level, start_trend
        seasonals = list(start_seasonals)
        sse = 0.0
        sses = []
        for value in values[m:]:
            old = seasonals.pop(0)
            base = level + phi * trend
            if multiplicative:
                sse += (value - base * old) ** 2
                new_level = alpha * value / old + (1 - alpha) * base
                if new_level <= 0:
                    break
                seasonals.append(gamma * value / new_level + (1 - gamma) * old)
            else:
                sse += (value - base - old) ** 2
                new_level = alpha * (value - old) + (1 - alpha) * base
                seasonals.append(gamma * (value - new_level) + (1 - gamma) * old)
            trend = beta * (new_level - level) + (1 - beta) * phi * trend
            level = new_level
            sses.append(sse)
        rows.append(((alpha, beta, gamma, phi), sses))
    out: dict[int, _Entry] = {}
    for k, params in _best_by_prefix(rows, wanted, m + 1).items():
        if params is None:
            out[k] = "no parameter set gives a positive multiplicative level"
        else:
            alpha, beta, gamma, phi = params
            out[k] = holt_winters_fit(values[:k], m, alpha, beta, gamma, phi, seasonal)
    return out


def holt_damped(history: Sequence[float]) -> float:
    """One-step forecast of the fitted damped Holt model."""
    return fit_holt_damped(history).forecast(1)


def holt_winters(history: Sequence[float], season_length: int, seasonal: str = "additive") -> float:
    """One-step forecast of the fitted Holt-Winters model."""
    return fit_holt_winters(history, season_length, seasonal).forecast(1)
