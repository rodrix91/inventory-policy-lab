"""Turn a :class:`~inventory_policy_lab.analysis.Report` into JSON or Markdown."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from . import __version__

if TYPE_CHECKING:  # pragma: no cover - imports for type hints only
    from .analysis import Config, Report, SkuResult

METHOD_ORDER = ("naive", "moving_average", "ses", "croston", "sba")
SIGMA_LABELS = {
    "demand": "standard deviation of demand per period",
    "rmse": "RMSE of the picked method on the holdout",
}


def _safety_stock_label(config: Config) -> str:
    if config.safety_stock_method == "bootstrap":
        return (
            "safety stock: bootstrap of protection-interval demand "
            f"({config.bootstrap_samples} samples, seed {config.seed})"
        )
    return f"safety-stock sigma: {SIGMA_LABELS[config.sigma]}"


def _r(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


def _sku_dict(result: SkuResult) -> dict[str, Any]:
    policy, sim, profile = result.policy, result.simulation, result.profile
    return {
        "sku": result.sku,
        "periods": result.periods,
        "filled_periods": result.filled_periods,
        "total_demand": _r(result.total_demand),
        "mean_demand": _r(result.mean_demand),
        "unit_cost": _r(result.unit_cost),
        "annual_value": _r(result.annual_value),
        "abc": result.abc,
        "xyz": result.xyz,
        "abc_xyz": result.abc_xyz,
        "cv": _r(result.cv),
        "profile": {
            "category": profile.category,
            "adi": _r(profile.adi),
            "cv2": _r(profile.cv2),
            "nonzero_periods": profile.nonzero_periods,
        },
        "forecast": {
            "method": result.method,
            "next_period": _r(result.forecast),
            "backtest": [
                {
                    "method": b.method,
                    "mae": _r(b.mae),
                    "rmse": _r(b.rmse),
                    "bias": _r(b.bias),
                    "mase": _r(b.mase),
                }
                for b in result.backtests
            ],
        },
        "policy": {
            "service_level": policy.service_level,
            "z": _r(policy.z),
            "demand_per_period": _r(policy.demand_per_period),
            "sigma_demand": _r(policy.sigma_demand),
            "lead_time": _r(policy.lead_time),
            "sigma_lead_time": _r(policy.sigma_lead_time),
            "review_period": _r(policy.review_period),
            "safety_stock": _r(policy.safety_stock),
            "safety_stock_method": policy.safety_stock_method,
            "reorder_point": _r(policy.reorder_point),
            "eoq": _r(policy.eoq),
            "order_quantity": _r(result.order_quantity),
            "order_quantity_source": result.order_quantity_source,
        },
        "simulation": {
            "periods": sim.periods,
            "lead_time_periods": sim.lead_time_periods,
            "total_demand": _r(sim.total_demand),
            "served_from_stock": _r(sim.served_from_stock),
            "fill_rate": _r(sim.fill_rate),
            "stockout_periods": sim.stockout_periods,
            "average_on_hand": _r(sim.average_on_hand),
            "orders_placed": sim.orders_placed,
            "max_backorder": _r(sim.max_backorder),
        },
        "notes": list(result.notes),
    }


def report_to_dict(report: Report) -> dict[str, Any]:
    """A JSON-ready dictionary with every number rounded to 4 decimals."""
    data, config = report.data, report.config
    return {
        "tool": "inventory-policy-lab",
        "version": __version__,
        "source": data.source,
        "rows": data.rows,
        "period_kind": data.period_kind,
        "periods": len(data.calendar),
        "first_period": data.calendar[0],
        "last_period": data.calendar[-1],
        "abc_basis": report.abc_basis,
        "settings": {
            "service_level": config.service_level,
            "class_service_levels": dict(config.class_service_levels),
            "holdout": config.holdout,
            "ma_window": config.ma_window,
            "ses_alpha": config.ses_alpha,
            "croston_alpha": config.croston_alpha,
            "periods_per_year": config.periods_per_year,
            "abc_thresholds": list(config.abc_thresholds),
            "xyz_thresholds": list(config.xyz_thresholds),
            "adi_cutoff": config.adi_cutoff,
            "cv2_cutoff": config.cv2_cutoff,
            "default_lead_time": config.lead_time,
            "default_lead_time_std": config.lead_time_std,
            "review_period": config.review_period,
            "ordering_cost": config.ordering_cost,
            "holding_rate": config.holding_rate,
            "order_cover": config.order_cover,
            "sigma": config.sigma,
            "safety_stock_method": config.safety_stock_method,
            "bootstrap_samples": config.bootstrap_samples,
            "seed": config.seed,
        },
        "summary": {
            "skus": len(report.skus),
            "abc_xyz": report.matrix(),
            "profiles": report.profile_counts(),
            "overall_fill_rate": _r(report.overall_fill_rate()),
        },
        "skus": [_sku_dict(result) for result in report.skus],
    }


def render_json(report: Report) -> str:
    return json.dumps(report_to_dict(report), indent=2, ensure_ascii=False) + "\n"


def _num(value: float | None, digits: int = 1) -> str:
    return "n/a" if value is None else f"{value:,.{digits}f}"


def _pct(value: float | None, digits: int = 1) -> str:
    return "n/a" if value is None else f"{value * 100:.{digits}f}%"


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return lines


def render_markdown(report: Report) -> str:
    """A human-readable report: settings, ABC-XYZ matrix, patterns, policy, backtest, notes."""
    data, config = report.data, report.config
    a, b = config.abc_thresholds
    x, y = config.xyz_thresholds
    basis = (
        "annual consumption value (units x unit cost)"
        if report.abc_basis == "value"
        else "annual units (no unit_cost column)"
    )
    levels = _pct(config.service_level, 0)
    if config.class_service_levels:
        per_class = ", ".join(
            f"{k} {_pct(v, 0)}" for k, v in sorted(config.class_service_levels.items())
        )
        levels += f" (by class: {per_class})"
    lines = [
        "# Inventory policy report",
        "",
        f"- Source: `{data.source}` ({data.rows} rows)",
        f"- SKUs: {len(report.skus)}; periods: {len(data.calendar)} ({data.period_kind}), "
        f"{data.calendar[0]} to {data.calendar[-1]}",
        f"- ABC by {basis}: A < {_pct(a, 0)} and B < {_pct(b, 0)} of cumulative value; "
        f"XYZ by CV: X <= {x:g}, Y <= {y:g}",
        f"- Target cycle service level: {levels}; review period: {config.review_period:g}; "
        f"holdout: last {config.holdout} periods; "
        f"{_safety_stock_label(config)}",
        f"- Replayed fill rate, all SKUs: {_pct(report.overall_fill_rate())}",
        "",
        "## ABC-XYZ matrix",
        "",
    ]
    matrix = report.matrix()
    rows = [
        [f"**{cls}**", *(str(matrix[cls][v]) for v in "XYZ"), str(sum(matrix[cls].values()))]
        for cls in "ABC"
    ]
    lines += _table(["", "X", "Y", "Z", "Total"], rows)
    lines += ["", "## Demand patterns (Syntetos-Boylan)", ""]
    counts = report.profile_counts()
    lines += _table(
        ["Pattern", "SKUs"],
        [[name, str(n)] for name, n in counts.items() if n or name != "no demand"],
    )
    lines += ["", "## Policy per SKU", ""]
    lines += _table(
        [
            "SKU",
            "Class",
            "Pattern",
            "Method",
            "Forecast/period",
            "CSL",
            "Safety stock",
            "Reorder point (s)",
            "Order qty (Q)",
            "Fill rate",
            "Stockout periods",
            "Avg on hand",
        ],
        [
            [
                r.sku,
                r.abc_xyz,
                r.profile.category,
                r.method,
                _num(r.forecast),
                _pct(r.policy.service_level, 0),
                _num(r.policy.safety_stock),
                _num(r.policy.reorder_point),
                f"{_num(r.order_quantity)} ({r.order_quantity_source})",
                _pct(r.simulation.fill_rate),
                f"{r.simulation.stockout_periods}/{r.simulation.periods}",
                _num(r.simulation.average_on_hand),
            ]
            for r in report.skus
        ],
    )
    lines += [
        "",
        f"## Forecast backtest (MASE, last {config.holdout} periods)",
        "",
        "Lower is better; below 1 beats the in-sample naive forecast. "
        "Intermittent and lumpy SKUs are scored with SES, Croston and SBA; "
        "the others with naive, moving average and SES.",
        "",
    ]
    backtest_rows = []
    for r in report.skus:
        scores = {bt.method: bt for bt in r.backtests}
        cells = []
        for name in METHOD_ORDER:
            result = scores.get(name)
            if result is None:
                cells.append("-")
            else:
                cell = _num(result.mase, 2)
                cells.append(f"**{cell}**" if name == r.method else cell)
        bias = scores[r.method].bias if r.method in scores else None
        backtest_rows.append([r.sku, *cells, _num(bias, 2)])
    lines += _table(["SKU", *METHOD_ORDER, "Bias of pick"], backtest_rows)
    noted = [r for r in report.skus if r.notes]
    if noted:
        lines += ["", "## Notes", ""]
        lines += [f"- {r.sku}: {'; '.join(r.notes)}" for r in noted]
    lines += [
        "",
        "Fill rate, stockout periods and average on hand come from replaying this same "
        "history under the (s, Q) policy (in-sample): a check of the formulas on the data, "
        "not a forecast of future service.",
        "",
    ]
    return "\n".join(lines)
