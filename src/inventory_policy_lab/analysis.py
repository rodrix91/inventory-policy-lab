"""Run the whole analysis for every SKU: classify, forecast, set the policy, replay it."""

from __future__ import annotations

import os
import statistics
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import partial
from typing import Any

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
from .policy import Policy, build_policy, eoq
from .reader import DemandData, SkuHistory, read_demand
from .simulate import SimulationResult, simulate

INTERMITTENT = ("intermittent", "lumpy")


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

    @property
    def abc_xyz(self) -> str:
        return self.abc + self.xyz


@dataclass(frozen=True)
class Report:
    data: DemandData
    config: Config
    abc_basis: str  # "value" or "quantity"
    skus: tuple[SkuResult, ...]

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


def _analyze_sku(history: SkuHistory, config: Config, abc: str, value: float) -> SkuResult:
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
    if len(series) >= config.holdout + 2:
        backtests = tuple(
            backtest(series, name, method, config.holdout) for name, method in candidates.items()
        )
        best = pick_best(backtests)
        method_name = best.method
        if best.mase is None:
            notes.append("MASE undefined (constant training data); method picked by MAE")
    else:
        notes.append(
            f"only {len(series)} period(s), fewer than holdout + 2 = {config.holdout + 2}: "
            f"no backtest, {method_name} used"
        )
    forecast = candidates[method_name](series)

    if config.sigma == "rmse" and best is not None:
        sigma_demand = best.rmse
    else:
        sigma_demand = statistics.stdev(series) if len(series) > 1 else 0.0
        if config.sigma == "rmse":
            notes.append("no backtest RMSE: demand standard deviation used for safety stock")
    lead, sigma_lead, lead_source = _lead_time(history, config)
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
    policy = build_policy(
        level, forecast, sigma_demand, lead, sigma_lead, eoq_units, config.review_period
    )

    if eoq_units is not None:
        quantity, quantity_source = eoq_units, "eoq"
    elif forecast * config.order_cover > 0:
        quantity, quantity_source = forecast * config.order_cover, "cover"
    else:
        quantity, quantity_source = 1.0, "minimum"
        notes.append("forecast is zero: order quantity set to 1 unit for the replay")
    simulation = simulate(series, policy.reorder_point, quantity, lead)

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
    return Report(data=data, config=config, abc_basis=basis, skus=results)


def analyze_file(path: str | os.PathLike[str], config: Config | None = None) -> Report:
    """Read ``path`` with :func:`read_demand` and :func:`analyze` it."""
    return analyze(read_demand(path), config)
