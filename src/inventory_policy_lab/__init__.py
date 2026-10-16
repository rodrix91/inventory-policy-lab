"""inventory-policy-lab: from demand history per SKU to a verified inventory policy.

Standard library only. The main entry points are :func:`analyze_file` (or
:func:`read_demand` + :func:`analyze`) and the renderers :func:`render_markdown`
and :func:`render_json`. ``Config(test_periods=N)`` adds an out-of-sample replay
(:func:`out_of_sample_replay`) to the report, and ``Config(trend_seasonal=True)``
adds damped Holt and Holt-Winters to the forecast candidates.
``Config(policy="RS")`` replays a periodic-review, order-up-to policy, and
``dynamic_levels=True`` lets its levels follow the forecast period by period.
``bootstrap_source="residuals"`` bootstraps the forecast errors instead of the
demand, and ``period_safety_stock=True`` gives each dynamic level its own
safety stock. ``order_cost``, ``holding_cost`` and ``stockout_cost`` price the
out-of-sample replay (:class:`CostRates`, :func:`replay_cost`).
"""

from __future__ import annotations

__version__ = "0.7.0"

from .analysis import Config, Report, SkuResult, analyze, analyze_file, replay_policy
from .classify import (
    DemandProfile,
    abc_classes,
    coefficient_of_variation,
    demand_profile,
    xyz_class,
)
from .costs import CostBreakdown, CostRates, replay_cost, total_cost
from .errors import (
    ConfigError,
    DataError,
    HistoryError,
    InputFileError,
    InventoryPolicyError,
)
from .forecast import BacktestResult, backtest, croston, moving_average, naive, sba, ses
from .policy import (
    Policy,
    bootstrap_safety_stock,
    build_policy,
    dynamic_levels,
    eoq,
    interval_demands,
    interval_forecast_errors,
    period_safety_stocks,
    protection_periods,
    residual_bootstrap_quantile,
    safety_stock,
)
from .reader import DemandData, SkuHistory, parse_rows, read_demand
from .render import render_json, render_markdown, report_to_dict
from .simulate import SimulationResult, simulate, simulate_periodic
from .smoothing import (
    FitCacheInfo,
    FitError,
    SmoothingFit,
    clear_fit_cache,
    fit_cache_info,
    fit_holt_damped,
    fit_holt_winters,
    holt_damped,
    holt_damped_fit,
    holt_winters,
    holt_winters_fit,
)
from .validation import (
    OutOfSampleReport,
    PolicyReplay,
    ReplayTotals,
    RollingReplay,
    SkuOutOfSample,
    out_of_sample_replay,
    train_history,
)

__all__ = [
    "BacktestResult",
    "Config",
    "ConfigError",
    "CostBreakdown",
    "CostRates",
    "DataError",
    "DemandData",
    "DemandProfile",
    "FitCacheInfo",
    "FitError",
    "HistoryError",
    "InputFileError",
    "InventoryPolicyError",
    "OutOfSampleReport",
    "Policy",
    "PolicyReplay",
    "ReplayTotals",
    "Report",
    "RollingReplay",
    "SimulationResult",
    "SkuHistory",
    "SkuOutOfSample",
    "SkuResult",
    "SmoothingFit",
    "__version__",
    "abc_classes",
    "analyze",
    "analyze_file",
    "backtest",
    "bootstrap_safety_stock",
    "interval_demands",
    "interval_forecast_errors",
    "period_safety_stocks",
    "protection_periods",
    "residual_bootstrap_quantile",
    "build_policy",
    "clear_fit_cache",
    "coefficient_of_variation",
    "croston",
    "demand_profile",
    "dynamic_levels",
    "eoq",
    "fit_cache_info",
    "fit_holt_damped",
    "fit_holt_winters",
    "holt_damped",
    "holt_damped_fit",
    "holt_winters",
    "holt_winters_fit",
    "moving_average",
    "naive",
    "out_of_sample_replay",
    "parse_rows",
    "read_demand",
    "render_json",
    "render_markdown",
    "replay_policy",
    "replay_cost",
    "report_to_dict",
    "safety_stock",
    "sba",
    "ses",
    "simulate",
    "simulate_periodic",
    "total_cost",
    "train_history",
    "xyz_class",
]
