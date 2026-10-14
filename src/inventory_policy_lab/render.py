"""Turn a :class:`~inventory_policy_lab.analysis.Report` into JSON or Markdown."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from . import __version__

if TYPE_CHECKING:  # pragma: no cover - imports for type hints only
    from .analysis import Config, Report, SkuResult
    from .simulate import SimulationResult
    from .validation import OutOfSampleReport, ReplayTotals

METHOD_ORDER = ("naive", "moving_average", "ses", "croston", "sba")
TREND_SEASONAL_ORDER = ("holt_damped", "hw_additive", "hw_multiplicative")
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


def _trend_seasonal_label(config: Config) -> str:
    from .smoothing import HOLT_MIN_HISTORY

    season = config.effective_season_length
    holt_winters = (
        "no Holt-Winters (no season length)"
        if season is None
        else f"Holt-Winters additive and multiplicative (multiplicative only without "
        f"zero-demand periods), season length {season}, from {2 * season} periods"
    )
    return (
        "- Trend and seasonal candidates for smooth and erratic SKUs: damped Holt from "
        f"{HOLT_MIN_HISTORY} periods before the first backtest origin; {holt_winters}; "
        "a picked model's forecast is its mean over the protection interval"
    )


def _r(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


def _sku_dict(result: SkuResult) -> dict[str, Any]:
    policy, sim, profile = result.policy, result.simulation, result.profile
    forecast: dict[str, Any] = {
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
    }
    if result.forecast_parameters is not None:
        forecast["parameters"] = dict(result.forecast_parameters)
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
        "forecast": forecast,
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
        "simulation": _simulation_dict(sim),
        "notes": list(result.notes),
    }


def _simulation_dict(sim: SimulationResult) -> dict[str, Any]:
    return {
        "periods": sim.periods,
        "lead_time_periods": sim.lead_time_periods,
        "total_demand": _r(sim.total_demand),
        "served_from_stock": _r(sim.served_from_stock),
        "fill_rate": _r(sim.fill_rate),
        "stockout_periods": sim.stockout_periods,
        "average_on_hand": _r(sim.average_on_hand),
        "orders_placed": sim.orders_placed,
        "max_backorder": _r(sim.max_backorder),
    }


def _totals_dict(totals: ReplayTotals) -> dict[str, Any]:
    return {
        "total_demand": _r(totals.total_demand),
        "served_from_stock": _r(totals.served_from_stock),
        "fill_rate": _r(totals.fill_rate),
        "stockout_periods": totals.stockout_periods,
        "average_on_hand": _r(totals.average_on_hand),
    }


def _out_of_sample_dict(oos: OutOfSampleReport) -> dict[str, Any]:
    from .validation import SAFETY_STOCK_METHODS

    return {
        "test_periods": oos.test_periods,
        "train": {
            "periods": len(oos.train_calendar),
            "first_period": oos.train_calendar[0],
            "last_period": oos.train_calendar[-1],
        },
        "test": {
            "periods": len(oos.test_calendar),
            "first_period": oos.test_calendar[0],
            "last_period": oos.test_calendar[-1],
        },
        "skipped_skus": list(oos.skipped),
        "summary": {
            method: {
                sample: _totals_dict(oos.totals(method, sample))
                for sample in ("in_sample", "out_of_sample")
            }
            for method in SAFETY_STOCK_METHODS
        },
        "skus": [
            {
                "sku": s.sku,
                "train_periods": s.train_periods,
                "test_periods": s.test_periods,
                "abc": s.abc,
                "category": s.category,
                "forecast_method": s.forecast_method,
                "forecast": _r(s.forecast),
                "policies": {
                    r.method: {
                        "safety_stock": _r(r.safety_stock),
                        "reorder_point": _r(r.reorder_point),
                        "order_quantity": _r(r.order_quantity),
                        "in_sample": _simulation_dict(r.in_sample),
                        "out_of_sample": _simulation_dict(r.out_of_sample),
                    }
                    for r in s.replays
                },
                "notes": list(s.notes),
            }
            for s in oos.skus
        ],
    }


def report_to_dict(report: Report) -> dict[str, Any]:
    """A JSON-ready dictionary with every number rounded to 4 decimals."""
    data, config = report.data, report.config
    result: dict[str, Any] = {
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
            "test_periods": config.test_periods,
            "trend_seasonal": config.trend_seasonal,
            "season_length": config.effective_season_length if config.trend_seasonal else None,
        },
        "summary": {
            "skus": len(report.skus),
            "abc_xyz": report.matrix(),
            "profiles": report.profile_counts(),
            "overall_fill_rate": _r(report.overall_fill_rate()),
        },
        "skus": [_sku_dict(result) for result in report.skus],
    }
    if report.out_of_sample is not None:
        result["out_of_sample"] = _out_of_sample_dict(report.out_of_sample)
    return result


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


def _out_of_sample_lines(oos: OutOfSampleReport) -> list[str]:
    from .validation import SAFETY_STOCK_METHODS

    train, test = oos.train_calendar, oos.test_calendar
    lines = [
        "",
        f"## Out-of-sample replay (train {train[0]} to {train[-1]}, test {test[0]} to {test[-1]})",
        "",
        f"Each policy is fitted on the first {len(train)} periods only (classes, forecast "
        "pick, sigma, lead times, bootstrap draws) and replayed over the whole history; "
        f"in-sample scores the {len(train)} training periods, out-of-sample only the last "
        f"{len(test)}, which start from the stock the policy left at the end of training.",
        "",
    ]
    rows = []
    for method in SAFETY_STOCK_METHODS:
        inside, outside = (oos.totals(method, s) for s in ("in_sample", "out_of_sample"))
        rows.append(
            [
                method,
                _pct(inside.fill_rate),
                _pct(outside.fill_rate),
                str(inside.stockout_periods),
                str(outside.stockout_periods),
                _num(inside.average_on_hand),
                _num(outside.average_on_hand),
            ]
        )
    lines += _table(
        [
            "Safety stock",
            "Fill rate, in-sample",
            "Fill rate, out-of-sample",
            "Stockout periods, in",
            "Stockout periods, out",
            "Avg on hand, in (sum)",
            "Avg on hand, out (sum)",
        ],
        rows,
    )
    lines += [""]
    sku_rows = []
    for s in oos.skus:
        normal, boot = s.replay("normal"), s.replay("bootstrap")
        sku_rows.append(
            [
                s.sku,
                s.abc,
                s.category,
                s.forecast_method,
                f"{_pct(normal.in_sample.fill_rate)} / {_pct(normal.out_of_sample.fill_rate)}",
                f"{_pct(boot.in_sample.fill_rate)} / {_pct(boot.out_of_sample.fill_rate)}",
                f"{normal.out_of_sample.stockout_periods} / {boot.out_of_sample.stockout_periods}",
                f"{_num(normal.out_of_sample.average_on_hand)} / "
                f"{_num(boot.out_of_sample.average_on_hand)}",
            ]
        )
    lines += _table(
        [
            "SKU",
            "Class (train)",
            "Pattern (train)",
            "Method",
            "Fill rate normal, in / out",
            "Fill rate bootstrap, in / out",
            "Stockout periods out, normal / bootstrap",
            "Avg on hand out, normal / bootstrap",
        ],
        sku_rows,
    )
    if oos.skipped:
        lines += [
            "",
            f"Not in the out-of-sample replay (no history before {test[0]}): "
            f"{', '.join(oos.skipped)}.",
        ]
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
    ]
    if config.trend_seasonal:
        lines.append(_trend_seasonal_label(config))
    lines += ["", "## ABC-XYZ matrix", ""]
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
    others = "naive, moving average and SES"
    order: tuple[str, ...] = METHOD_ORDER
    if config.trend_seasonal:
        others = "naive, moving average, SES, damped Holt and Holt-Winters when the history allows"
        order = METHOD_ORDER + TREND_SEASONAL_ORDER
    lines += [
        "",
        f"## Forecast backtest (MASE, last {config.holdout} periods)",
        "",
        "Lower is better; below 1 beats the in-sample naive forecast. "
        "Intermittent and lumpy SKUs are scored with SES, Croston and SBA; "
        f"the others with {others}.",
        "",
    ]
    backtest_rows = []
    for r in report.skus:
        scores = {bt.method: bt for bt in r.backtests}
        cells = []
        for name in order:
            result = scores.get(name)
            if result is None:
                cells.append("-")
            else:
                cell = _num(result.mase, 2)
                cells.append(f"**{cell}**" if name == r.method else cell)
        bias = scores[r.method].bias if r.method in scores else None
        backtest_rows.append([r.sku, *cells, _num(bias, 2)])
    lines += _table(["SKU", *order, "Bias of pick"], backtest_rows)
    if report.out_of_sample is not None:
        lines += _out_of_sample_lines(report.out_of_sample)
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
