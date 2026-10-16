"""Run the whole analysis for every SKU: classify, forecast, set the policy, replay it."""

from __future__ import annotations

import math
import os
import random
import statistics
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING, Any

from .classify import (
    ADI_CUTOFF,
    CV2_CUTOFF,
    DemandProfile,
    abc_classes,
    coefficient_of_variation,
    demand_profile,
    xyz_class,
)
from .errors import ConfigError, DataError, HistoryError
from .forecast import (
    BacktestResult,
    Method,
    backtest,
    croston,
    moving_average,
    naive,
    pick_best,
    sba,
    ses,
)
from .policy import (
    BOOTSTRAP_SOURCES,
    POLICY_KINDS,
    IntervalForecaster,
    Policy,
    bootstrap_safety_stock,
    build_policy,
    dynamic_levels,
    eoq,
    interval_forecast_errors,
    period_safety_stocks,
    protection_periods,
    residual_bootstrap_quantile,
)
from .reader import DemandData, SkuHistory, read_demand
from .simulate import SimulationResult, simulate, simulate_periodic
from .smoothing import (
    HOLT_MIN_HISTORY,
    FitError,
    SmoothingFit,
    fit_holt_damped,
    fit_holt_winters,
)

if TYPE_CHECKING:  # pragma: no cover - imports for type hints only
    from .validation import OutOfSampleReport

INTERMITTENT = ("intermittent", "lumpy")
TREND_SEASONAL = ("holt_damped", "hw_additive", "hw_multiplicative")

Fitter = Callable[[Sequence[float]], SmoothingFit]


@dataclass(frozen=True)
class Config:
    """Settings of one analysis. Lead times and the holdout are in periods."""

    service_level: float = 0.95
    class_service_levels: Mapping[str, float] = field(default_factory=dict)
    holdout: int = 6
    ma_window: int = 3
    ses_alpha: float = 0.2
    croston_alpha: float = 0.1
    periods_per_year: float = 12.0
    abc_thresholds: tuple[float, float] = (0.80, 0.95)
    xyz_thresholds: tuple[float, float] = (0.5, 1.0)
    adi_cutoff: float = ADI_CUTOFF
    cv2_cutoff: float = CV2_CUTOFF
    lead_time: float = 1.0
    lead_time_std: float = 0.0
    review_period: float = 1.0
    ordering_cost: float | None = None
    holding_rate: float | None = None
    order_cover: float = 1.0
    sigma: str = "demand"
    safety_stock_method: str = "normal"
    bootstrap_samples: int = 2000
    seed: int = 0
    test_periods: int = 0  # last periods kept out for the out-of-sample replay; 0 = off
    trend_seasonal: bool = False  # add damped Holt and Holt-Winters candidates (ADR 0006)
    season_length: int | None = None  # None: periods_per_year when it is a whole number
    policy: str = "sQ"  # "sQ" (reorder point, fixed quantity) or "RS" (order-up-to, ADR 0007)
    dynamic_levels: bool = False  # levels that follow a trend or seasonal forecast (ADR 0007)
    bootstrap_source: str = "demand"  # bootstrap "demand" or forecast "residuals" (ADR 0008)
    period_safety_stock: bool = False  # safety stock per period with dynamic levels (ADR 0008)
    rolling_origin: bool = False  # also refit every test period out of sample (ADR 0009)
    refit_every: int = 1  # rolling origin: refit every K test periods only (ADR 0011)

    @property
    def effective_season_length(self) -> int | None:
        """Season of the Holt-Winters candidates: the setting, else one year of periods."""
        if self.season_length is not None:
            return self.season_length
        if self.periods_per_year >= 2 and float(self.periods_per_year).is_integer():
            return int(self.periods_per_year)
        return None

    def validate(self) -> None:
        """Raise :class:`ConfigError` for any setting out of range."""
        levels = {"service_level": self.service_level}
        for name, level in self.class_service_levels.items():
            if name not in ("A", "B", "C"):
                raise ConfigError(f"class service levels apply to A, B and C, not {name!r}")
            levels[f"service level of class {name}"] = level
        for label, level in levels.items():
            if not 0.5 <= level < 1:
                raise ConfigError(f"{label} must be at least 0.5 and below 1, got {level}")
        if self.holdout < 1:
            raise ConfigError(f"holdout must be at least 1 period, got {self.holdout}")
        if self.ma_window < 1:
            raise ConfigError(f"moving-average window must be at least 1, got {self.ma_window}")
        for label, alpha in (("ses alpha", self.ses_alpha), ("croston alpha", self.croston_alpha)):
            if not 0 < alpha <= 1:
                raise ConfigError(f"{label} must be in (0, 1], got {alpha}")
        if self.periods_per_year <= 0:
            raise ConfigError(f"periods per year must be positive, got {self.periods_per_year}")
        for label, (low, high) in (
            ("ABC thresholds", self.abc_thresholds),
            ("XYZ thresholds", self.xyz_thresholds),
        ):
            if not 0 < low < high:
                raise ConfigError(f"{label} must satisfy 0 < first < second, got {low}, {high}")
        if self.abc_thresholds[1] > 1:
            raise ConfigError("ABC thresholds are cumulative shares and cannot exceed 1")
        if self.lead_time < 0 or self.lead_time_std < 0:
            raise ConfigError("lead time and its standard deviation cannot be negative")
        if self.review_period < 0:
            raise ConfigError(f"review period cannot be negative, got {self.review_period}")
        if (self.ordering_cost is None) != (self.holding_rate is None):
            raise ConfigError("EOQ needs both an ordering cost and a holding rate")
        if self.ordering_cost is not None and self.ordering_cost < 0:
            raise ConfigError(f"ordering cost cannot be negative, got {self.ordering_cost}")
        if self.holding_rate is not None and self.holding_rate <= 0:
            raise ConfigError(f"holding rate must be positive, got {self.holding_rate}")
        if self.order_cover <= 0:
            raise ConfigError(f"order cover must be positive, got {self.order_cover}")
        if self.sigma not in ("demand", "rmse"):
            raise ConfigError(f"sigma must be 'demand' or 'rmse', got {self.sigma!r}")
        if self.safety_stock_method not in ("normal", "bootstrap"):
            raise ConfigError(
                "safety-stock method must be 'normal' or 'bootstrap', "
                f"got {self.safety_stock_method!r}"
            )
        if self.bootstrap_samples < 100:
            raise ConfigError(
                f"bootstrap samples must be at least 100, got {self.bootstrap_samples}"
            )
        if self.test_periods < 0:
            raise ConfigError(f"test periods cannot be negative, got {self.test_periods}")
        if self.season_length is not None:
            if not self.trend_seasonal:
                raise ConfigError(
                    "a season length only applies with trend_seasonal (--trend-seasonal)"
                )
            if self.season_length < 2:
                raise ConfigError(f"season length must be at least 2, got {self.season_length}")
        if self.policy not in POLICY_KINDS:
            raise ConfigError(f"policy must be 'sQ' or 'RS', got {self.policy!r}")
        if self.policy == "RS" and not (
            self.review_period >= 1 and float(self.review_period).is_integer()
        ):
            raise ConfigError(
                "an (R, S) policy needs a whole review period of at least 1, "
                f"got {self.review_period}"
            )
        if self.dynamic_levels and not self.trend_seasonal:
            raise ConfigError(
                "dynamic levels follow a trend or seasonal forecast and need "
                "trend_seasonal (--trend-seasonal)"
            )
        if self.bootstrap_source not in BOOTSTRAP_SOURCES:
            raise ConfigError(
                f"bootstrap source must be 'demand' or 'residuals', got {self.bootstrap_source!r}"
            )
        if (
            self.bootstrap_source == "residuals"
            and self.safety_stock_method != "bootstrap"
            and not self.test_periods
        ):
            raise ConfigError(
                "the residual bootstrap only applies to a bootstrap safety stock "
                "(--safety-stock bootstrap, or the bootstrap replay of --test-periods)"
            )
        if self.period_safety_stock and not (
            self.dynamic_levels and self.bootstrap_source == "residuals"
        ):
            raise ConfigError(
                "a safety stock per period needs dynamic levels and the residual bootstrap "
                "(--dynamic-levels --bootstrap-source residuals)"
            )
        if self.rolling_origin and not self.test_periods:
            raise ConfigError(
                "the rolling-origin replay refits the policy in the test window and "
                "needs test periods (--test-periods N)"
            )
        if self.refit_every < 1:
            raise ConfigError(f"refit every must be at least 1 period, got {self.refit_every}")
        if self.refit_every != 1 and not self.rolling_origin:
            raise ConfigError(
                "refitting every K periods applies to the rolling-origin replay (--rolling-origin)"
            )

    def methods(self, category: str) -> dict[str, Method]:
        """Candidate forecasting methods for a demand category, in tie-break order."""
        smoothing: Method = partial(ses, alpha=self.ses_alpha)
        if category in INTERMITTENT:
            # Naive and moving averages are left out on purpose: on mostly-zero
            # series they forecast zero after a run of zeros, which scores well on
            # error measures but means holding no stock (ADR 0002).
            return {
                "ses": smoothing,
                "croston": partial(croston, alpha=self.croston_alpha),
                "sba": partial(sba, alpha=self.croston_alpha),
            }
        return {
            "naive": naive,
            "moving_average": partial(moving_average, window=self.ma_window),
            "ses": smoothing,
        }

    def trend_seasonal_fitters(
        self, category: str, fit_length: int, positive: bool
    ) -> dict[str, Fitter]:
        """Damped Holt and Holt-Winters fitters a SKU can use, in tie-break order.

        ``fit_length`` is the shortest history a fit will see (the periods before
        the first backtest origin) and ``positive`` says whether every period has
        demand. Nothing is returned without ``trend_seasonal`` or for intermittent
        and lumpy SKUs; damped Holt needs ``HOLT_MIN_HISTORY`` periods and
        Holt-Winters two full seasons, the multiplicative form demand in every period.
        """
        if not self.trend_seasonal or category in INTERMITTENT:
            return {}
        fitters: dict[str, Fitter] = {}
        if fit_length >= HOLT_MIN_HISTORY:
            fitters["holt_damped"] = fit_holt_damped
        season = self.effective_season_length
        if season is not None and fit_length >= 2 * season:
            fitters["hw_additive"] = partial(
                fit_holt_winters, season_length=season, seasonal="additive"
            )
            if positive:
                fitters["hw_multiplicative"] = partial(
                    fit_holt_winters, season_length=season, seasonal="multiplicative"
                )
        return fitters


def _one_step(fitter: Fitter) -> Method:
    def method(history: Sequence[float]) -> float:
        return fitter(history).forecast(1)

    return method


def _level_interval(method: Method) -> IntervalForecaster:
    """Total forecast of the next ``P`` periods of a level method: ``P`` times its forecast."""

    def forecaster(history: Sequence[float], periods: int) -> float | None:
        return periods * method(history)

    return forecaster


def _fit_interval(fitter: Fitter) -> IntervalForecaster:
    """Total forecast of the next ``P`` periods of a model refitted on ``history``.

    ``None`` (origin skipped) when the history is too short for the model or no
    valid fit exists, the same condition that keeps the model out of a backtest.
    """

    def forecaster(history: Sequence[float], periods: int) -> float | None:
        try:
            fit = fitter(history)
        except ValueError:  # too short, or FitError (a ValueError) for no valid fit
            return None
        return math.fsum(fit.forecast(h) for h in range(1, periods + 1))

    return forecaster


# The earliest origin of the residual errors: the two training periods the
# backtest needs; models that need more history skip the origins before it.
RESIDUAL_START = 2


@dataclass(frozen=True)
class _Residuals:
    """The safety stock from the residual bootstrap and how it was obtained."""

    safety_stock: float  # static, floored at zero
    relative: float | None  # quantile of relative errors, with a safety stock per period
    notes: tuple[str, ...]


def _residual_safety_stock(
    series: Sequence[float],
    forecaster: IntervalForecaster,
    forecast: float,
    lead: float,
    lead_times: Sequence[float],
    level: float,
    config: Config,
    rng: random.Random,
    per_period: bool = False,
) -> _Residuals | None:
    """Bootstrap of the rolling-origin forecast errors over ``L + R``; ``None`` without errors.

    With ``per_period`` the errors are relative to the forecast and the static
    safety stock is that quantile times the forecast over the interval; when no
    origin has a positive forecast it falls back to the absolute errors, with a
    note.
    """
    lengths = {protection_periods(t, config.review_period) for t in lead_times or (lead,)}
    protection = lead + config.review_period
    for relative in (True, False) if per_period else (False,):
        errors = {
            p: interval_forecast_errors(series, forecaster, p, RESIDUAL_START, relative)
            for p in lengths
        }
        try:
            quantile = residual_bootstrap_quantile(
                errors,
                level,
                lead,
                config.review_period,
                lead_times,
                config.bootstrap_samples,
                rng,
            )
        except ValueError:
            continue
        counts = ", ".join(f"{len(errors[p])} over {p}" for p in sorted(lengths) if p)
        kind = "relative forecast errors" if relative else "forecast errors"
        notes = [f"residual bootstrap: rolling-origin {kind} ({counts} period(s))"]
        if relative != per_period:
            notes.append("no positive forecast at any origin: one safety stock for every period")
        if quantile < 0:
            notes.append("residual quantile below zero: safety stock floored at 0")
        if relative:
            return _Residuals(max(quantile, 0.0) * forecast * protection, quantile, tuple(notes))
        return _Residuals(max(quantile, 0.0), None, tuple(notes))
    return None


def _trend_seasonal_candidate(
    series: Sequence[float], name: str, fitter: Fitter, holdout: int
) -> tuple[BacktestResult, SmoothingFit] | None:
    """Backtest and final fit of one trend or seasonal model; ``None`` if a fit fails."""
    try:
        final = fitter(series)
        result = backtest(series, name, _one_step(fitter), holdout)
    except FitError:
        return None
    return result, final


def replay_policy(
    demand: Sequence[float],
    policy: Policy,
    order_quantity: float | Sequence[float],
    levels: Sequence[float] = (),
    warmup: int = 0,
) -> SimulationResult:
    """Replay ``demand`` under ``policy``: (s, Q) or (R, S), static or with ``levels``.

    ``levels`` (one per period of ``demand``) replace the policy's single level
    when given. ``order_quantity`` is one quantity or one per period. An (R, S)
    policy ignores ``order_quantity``.
    """
    level: float | Sequence[float] = levels if levels else policy.reorder_point
    if policy.kind == "RS":
        review = int(policy.review_period)
        return simulate_periodic(demand, level, review, policy.lead_time, warmup=warmup)
    return simulate(demand, level, order_quantity, policy.lead_time, warmup=warmup)


@dataclass(frozen=True)
class SkuResult:
    sku: str
    periods: int
    filled_periods: int
    total_demand: float
    mean_demand: float
    unit_cost: float | None
    annual_value: float  # annual consumption value (or annual units without unit costs)
    abc: str
    cv: float | None
    xyz: str
    profile: DemandProfile
    backtests: tuple[BacktestResult, ...]
    method: str
    forecast: float
    policy: Policy
    order_quantity: float
    order_quantity_source: str  # "eoq", "cover" or "minimum"
    simulation: SimulationResult
    notes: tuple[str, ...]
    forecast_parameters: Mapping[str, float] | None = None  # smoothing parameters picked
    levels: tuple[float, ...] = ()  # dynamic levels of the replayed periods; () when static
    next_levels: tuple[float, ...] = ()  # dynamic levels of the periods after the history
    safety_stocks: tuple[float, ...] = ()  # per-period safety stocks of the replayed periods
    next_safety_stocks: tuple[float, ...] = ()  # per-period safety stocks after the history

    @property
    def abc_xyz(self) -> str:
        return self.abc + self.xyz


@dataclass(frozen=True)
class Report:
    data: DemandData
    config: Config
    abc_basis: str  # "value" or "quantity"
    skus: tuple[SkuResult, ...]
    out_of_sample: OutOfSampleReport | None = None  # with Config.test_periods > 0

    def matrix(self) -> dict[str, dict[str, int]]:
        """Count of SKUs in each ABC-XYZ cell."""
        counts = {a: dict.fromkeys("XYZ", 0) for a in "ABC"}
        for result in self.skus:
            counts[result.abc][result.xyz] += 1
        return counts

    def profile_counts(self) -> dict[str, int]:
        names = ("smooth", "erratic", "intermittent", "lumpy", "no demand")
        counts = dict.fromkeys(names, 0)
        for result in self.skus:
            counts[result.profile.category] += 1
        return counts

    def overall_fill_rate(self) -> float | None:
        demand = sum(r.simulation.total_demand for r in self.skus)
        served = sum(r.simulation.served_from_stock for r in self.skus)
        return served / demand if demand > 0 else None

    def to_dict(self) -> dict[str, Any]:
        from .render import report_to_dict

        return report_to_dict(self)


def _lead_time(history: SkuHistory, config: Config) -> tuple[float, float, str]:
    observed = history.lead_times
    if not observed:
        return config.lead_time, config.lead_time_std, "default"
    sigma = statistics.stdev(observed) if len(observed) > 1 else 0.0
    return statistics.fmean(observed), sigma, "observed"


def _analyze_sku(
    history: SkuHistory, config: Config, abc: str, value: float, horizon: int | None = None
) -> SkuResult:
    """One SKU. With dynamic levels, ``horizon`` periods after the history get levels
    too (``next_levels``); by default one season (one period without a season)."""
    series = history.demand
    notes: list[str] = []
    if history.filled_periods:
        notes.append(f"{history.filled_periods} period(s) without rows counted as zero demand")
    cv = coefficient_of_variation(series)
    profile = demand_profile(series, config.adi_cutoff, config.cv2_cutoff)
    candidates = config.methods(profile.category)

    best: BacktestResult | None = None
    backtests: tuple[BacktestResult, ...] = ()
    method_name = "ses" if profile.category in INTERMITTENT else "moving_average"
    fits: dict[str, SmoothingFit] = {}
    fitters: dict[str, Fitter] = {}
    if len(series) >= config.holdout + 2:
        backtests = tuple(
            backtest(series, name, method, config.holdout) for name, method in candidates.items()
        )
        fitters = config.trend_seasonal_fitters(
            profile.category, len(series) - config.holdout, min(series) > 0
        )
        for name, fitter in fitters.items():
            candidate = _trend_seasonal_candidate(series, name, fitter, config.holdout)
            if candidate is None:
                notes.append(f"{name}: no valid fit (level not positive), left out")
                continue
            backtests += (candidate[0],)
            fits[name] = candidate[1]
        best = pick_best(backtests)
        method_name = best.method
        if best.mase is None:
            notes.append("MASE undefined (constant training data); method picked by MAE")
    else:
        notes.append(
            f"only {len(series)} period(s), fewer than holdout + 2 = {config.holdout + 2}: "
            f"no backtest, {method_name} used"
        )
    lead, sigma_lead, lead_source = _lead_time(history, config)
    parameters = None
    if method_name in fits:
        # A trend or seasonal forecast changes from period to period; the static
        # policy uses its mean over the protection interval, in whole periods.
        fit = fits[method_name]
        forecast = fit.mean_forecast(int(lead + config.review_period + 0.5))
        parameters = fit.parameters()
    else:
        forecast = candidates[method_name](series)

    if config.sigma == "rmse" and best is not None:
        sigma_demand = best.rmse
    else:
        sigma_demand = statistics.stdev(series) if len(series) > 1 else 0.0
        if config.sigma == "rmse":
            notes.append("no backtest RMSE: demand standard deviation used for safety stock")
    if lead_source == "default":
        notes.append("no observed lead times: default lead time used")

    eoq_units = None
    if config.ordering_cost is not None and config.holding_rate is not None:
        assert history.unit_cost is not None  # checked in analyze()
        eoq_units = eoq(
            forecast * config.periods_per_year,
            config.ordering_cost,
            config.holding_rate * history.unit_cost,
        )
    level = config.class_service_levels.get(abc, config.service_level)
    bootstrap_units = None
    relative_error: float | None = None
    residuals: _Residuals | None = None
    # One generator per SKU, seeded by the run seed and the SKU name, so a
    # SKU's result does not depend on which other SKUs are in the file.
    rng = random.Random(f"{config.seed}:{history.sku}")
    if config.safety_stock_method == "bootstrap":
        if config.bootstrap_source == "residuals":
            forecaster = (
                _fit_interval(fitters[method_name])
                if method_name in fits
                else _level_interval(candidates[method_name])
            )
            # A safety stock per period only where the levels move: with a level
            # forecast every period has the same forecast, so it stays one number.
            per_period = config.period_safety_stock and method_name in fits
            if config.period_safety_stock and not per_period:
                notes.append("level forecast picked: one safety stock for every period")
            residuals = _residual_safety_stock(
                series,
                forecaster,
                forecast,
                lead,
                history.lead_times,
                level,
                config,
                rng,
                per_period,
            )
            if residuals is None:
                notes.append(
                    "too little history for forecast errors over the protection interval: "
                    "bootstrap of demand used"
                )
            else:
                notes += residuals.notes
                bootstrap_units, relative_error = residuals.safety_stock, residuals.relative
    if config.safety_stock_method == "bootstrap" and residuals is None:
        quantile, bootstrap_units = bootstrap_safety_stock(
            series,
            level,
            forecast,
            lead,
            config.review_period,
            history.lead_times,
            config.bootstrap_samples,
            rng,
        )
        if bootstrap_units == 0 and quantile < forecast * (lead + config.review_period):
            notes.append(
                "bootstrap quantile below the forecast over the protection interval: "
                "safety stock floored at 0"
            )
    policy = build_policy(
        level,
        forecast,
        sigma_demand,
        lead,
        sigma_lead,
        eoq_units,
        config.review_period,
        bootstrap_units,
        config.policy,
    )

    if eoq_units is not None:
        quantity, quantity_source = eoq_units, "eoq"
    elif forecast * config.order_cover > 0:
        quantity, quantity_source = forecast * config.order_cover, "cover"
    else:
        quantity, quantity_source = 1.0, "minimum"
        if config.policy == "sQ":
            notes.append("forecast is zero: order quantity set to 1 unit for the replay")

    levels: tuple[float, ...] = ()
    next_levels: tuple[float, ...] = ()
    stocks: tuple[float, ...] = ()
    next_stocks: tuple[float, ...] = ()
    if config.dynamic_levels:
        ahead = horizon if horizon is not None else (config.effective_season_length or 1)
        steps = max(int(lead + config.review_period + 0.5), 1)
        span = len(series) + ahead + steps
        if method_name in fits:
            forecasts = fits[method_name].calendar_forecasts(len(series), span)
        else:
            forecasts = (forecast,) * span
            notes.append("level forecast picked: dynamic levels equal the static level")
        periods = len(series) + ahead
        safety: float | tuple[float, ...] = policy.safety_stock
        if relative_error is not None:
            safety = period_safety_stocks(
                forecasts, periods, lead, config.review_period, relative_error
            )
            stocks, next_stocks = safety[: len(series)], safety[len(series) :]
        every = dynamic_levels(forecasts, periods, lead, config.review_period, safety)
        levels, next_levels = every[: len(series)], every[len(series) :]
    simulation = replay_policy(series, policy, quantity, levels)

    return SkuResult(
        sku=history.sku,
        periods=len(series),
        filled_periods=history.filled_periods,
        total_demand=float(sum(series)),
        mean_demand=statistics.fmean(series),
        unit_cost=history.unit_cost,
        annual_value=value,
        abc=abc,
        cv=cv,
        xyz=xyz_class(cv, *config.xyz_thresholds),
        profile=profile,
        backtests=backtests,
        method=method_name,
        forecast=forecast,
        policy=policy,
        order_quantity=quantity,
        order_quantity_source=quantity_source,
        simulation=simulation,
        notes=tuple(notes),
        forecast_parameters=parameters,
        levels=levels,
        next_levels=next_levels,
        safety_stocks=stocks,
        next_safety_stocks=next_stocks,
    )


def analyze(data: DemandData, config: Config | None = None) -> Report:
    """Analyze already-read demand data. Raises :class:`InventoryPolicyError` subclasses."""
    config = config or Config()
    config.validate()
    if len(data.calendar) < config.holdout + 2:
        raise HistoryError(
            f"the file covers {len(data.calendar)} period(s); a holdout of {config.holdout} "
            f"needs at least {config.holdout + 2}. Lower --holdout or add history"
        )
    without_cost = [h.sku for h in data.skus if h.unit_cost is None]
    if data.has_unit_cost and without_cost:
        raise DataError(f"unit_cost is empty for every row of sku(s): {', '.join(without_cost)}")
    if config.ordering_cost is not None and not data.has_unit_cost:
        raise DataError("EOQ needs a unit_cost column to turn the holding rate into a cost")

    basis = "value" if data.has_unit_cost else "quantity"
    values = {
        h.sku: statistics.fmean(h.demand)
        * config.periods_per_year
        * (h.unit_cost if h.unit_cost is not None else 1.0)
        for h in data.skus
    }
    classes = abc_classes(values, *config.abc_thresholds)
    results = tuple(_analyze_sku(h, config, classes[h.sku], values[h.sku]) for h in data.skus)
    out_of_sample = None
    if config.test_periods:
        from .validation import out_of_sample_replay

        out_of_sample = out_of_sample_replay(data, config)
    return Report(
        data=data, config=config, abc_basis=basis, skus=results, out_of_sample=out_of_sample
    )


def analyze_file(path: str | os.PathLike[str], config: Config | None = None) -> Report:
    """Read ``path`` with :func:`read_demand` and :func:`analyze` it."""
    return analyze(read_demand(path), config)
