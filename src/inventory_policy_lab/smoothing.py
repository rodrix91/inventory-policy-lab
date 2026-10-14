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
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import product

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


def fit_holt_damped(history: Sequence[float]) -> SmoothingFit:
    """Damped Holt with the grid parameters of lowest in-sample SSE (first on ties)."""
    if len(history) < HOLT_MIN_HISTORY:
        raise ValueError(f"damped Holt is fitted on at least {HOLT_MIN_HISTORY} periods")
    best: SmoothingFit | None = None
    for alpha, beta, phi in product(ALPHAS, BETAS, PHIS):
        fit = holt_damped_fit(history, alpha, beta, phi)
        if best is None or fit.sse < best.sse:
            best = fit
    assert best is not None  # the grids are not empty
    return best


def fit_holt_winters(
    history: Sequence[float], season_length: int, seasonal: str = "additive"
) -> SmoothingFit:
    """Holt-Winters with the grid parameters of lowest in-sample SSE (first on ties).

    Parameter sets whose multiplicative level is not positive are skipped; when
    none is left (or the history has a zero), :class:`FitError` is raised.
    """
    if seasonal == "multiplicative" and min(history, default=0) <= 0:
        raise FitError("multiplicative Holt-Winters needs demand above zero in every period")
    best: SmoothingFit | None = None
    for alpha, beta, gamma, phi in product(ALPHAS, BETAS, GAMMAS, PHIS):
        try:
            fit = holt_winters_fit(history, season_length, alpha, beta, gamma, phi, seasonal)
        except FitError:
            continue
        if best is None or fit.sse < best.sse:
            best = fit
    if best is None:
        raise FitError("no parameter set gives a positive multiplicative level")
    return best


def holt_damped(history: Sequence[float]) -> float:
    """One-step forecast of the fitted damped Holt model."""
    return fit_holt_damped(history).forecast(1)


def holt_winters(history: Sequence[float], season_length: int, seasonal: str = "additive") -> float:
    """One-step forecast of the fitted Holt-Winters model."""
    return fit_holt_winters(history, season_length, seasonal).forecast(1)
