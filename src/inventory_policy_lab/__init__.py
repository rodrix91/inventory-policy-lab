"""inventory-policy-lab: from demand history per SKU to a verified inventory policy.

Standard library only. The main entry points are :func:`analyze_file` (or
:func:`read_demand` + :func:`analyze`) and the renderers :func:`render_markdown`
and :func:`render_json`.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .analysis import Config, Report, SkuResult, analyze, analyze_file
from .classify import (
    DemandProfile,
    abc_classes,
    coefficient_of_variation,
    demand_profile,
    xyz_class,
)
from .errors import (
    ConfigError,
    DataError,
    HistoryError,
    InputFileError,
    InventoryPolicyError,
)
from .forecast import BacktestResult, backtest, croston, moving_average, naive, sba, ses
from .policy import Policy, bootstrap_safety_stock, build_policy, eoq, safety_stock
from .reader import DemandData, SkuHistory, parse_rows, read_demand
from .render import render_json, render_markdown, report_to_dict
from .simulate import SimulationResult, simulate

__all__ = [
    "BacktestResult",
    "Config",
    "ConfigError",
    "DataError",
    "DemandData",
    "DemandProfile",
    "HistoryError",
    "InputFileError",
    "InventoryPolicyError",
    "Policy",
    "Report",
    "SimulationResult",
    "SkuHistory",
    "SkuResult",
    "__version__",
    "abc_classes",
    "analyze",
    "analyze_file",
    "backtest",
    "bootstrap_safety_stock",
    "build_policy",
    "coefficient_of_variation",
    "croston",
    "demand_profile",
    "eoq",
    "moving_average",
    "naive",
    "parse_rows",
    "read_demand",
    "render_json",
    "render_markdown",
    "report_to_dict",
    "safety_stock",
    "sba",
    "ses",
    "simulate",
    "xyz_class",
]
