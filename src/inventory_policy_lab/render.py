"""Turn a :class:`~inventory_policy_lab.analysis.Report` into JSON or Markdown."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from . import __version__

if TYPE_CHECKING:  # pragma: no cover - imports for type hints only
    from .analysis import Config, Report, SkuResult
    from .costs import CostBreakdown, CostRates
    from .optimize import CostSearch
    from .policy import Policy
    from .simulate import SimulationResult
    from .validation import OutOfSampleReport, PolicyReplay, ReplayTotals, RollingReplay

METHOD_ORDER = ("naive", "moving_average", "ses", "croston", "sba")
TREND_SEASONAL_ORDER = ("holt_damped", "hw_additive", "hw_multiplicative")
SIGMA_LABELS = {
    "demand": "standard deviation of demand per period",
    "rmse": "RMSE of the picked method on the holdout",
}


def _safety_stock_label(config: Config) -> str:
    if config.safety_stock_method == "bootstrap" and config.bootstrap_source == "residuals":
        label = (
            "safety stock: bootstrap of rolling-origin forecast errors over the protection "
            f"interval ({config.bootstrap_samples} samples, seed {config.seed})"
        )
        if config.period_safety_stock:
            label += "; one safety stock per period, proportional to the forecast"
        return label
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


def _rs(values: tuple[float, ...]) -> list[float]:
    return [round(value, 4) for value in values]


POLICY_NAMES = {"sQ": "(s, Q)", "RS": "(R, S)", "RsS": "(R, s, S)"}


def _policy_name(config: Config) -> str:
    return POLICY_NAMES[config.policy]


def _policy_label(config: Config) -> str:
    if config.policy == "RS":
        label = (
            "- Policy: (R, S) periodic review, order-up-to level S = D x (L + R) + SS, "
            f"reviewed every {config.review_period:g} period(s)"
        )
    elif config.policy == "RsS":
        label = (
            "- Policy: (R, s, S) periodic review, reorder level s = D x (L + R) + SS, "
            "order-up-to level S = s + Q, ordering only when the position is at or below s, "
            f"reviewed every {config.review_period:g} period(s)"
        )
    else:
        label = "- Policy: (s, Q) reorder point s = D x (L + R) + SS, fixed order quantity Q"
    if config.dynamic_levels:
        level = "S" if config.policy == "RS" else "s"
        label += (
            f"; dynamic levels: {level} follows the forecast period by period, "
            f"{level}(t) = mean forecast of the next L + R periods x (L + R) + SS"
        )
    return label


def _level_dict(policy: Policy, quantity: float, source: str) -> dict[str, Any]:
    """The level and quantity keys of a policy: (s, Q) as before, (R, S) with S."""
    if policy.kind == "RsS":
        return {
            "kind": "RsS",
            "order_up_to": _r(policy.reorder_point + quantity),
            "reorder_point": _r(policy.reorder_point),
            "order_quantity": _r(quantity),
            "order_quantity_source": source,
        }
    if policy.kind == "RS":
        return {
            "kind": "RS",
            "order_up_to": _r(policy.reorder_point),
            "reorder_point": None,
            "order_quantity": None,
            "order_quantity_source": None,
        }
    return {
        "reorder_point": _r(policy.reorder_point),
        "order_quantity": _r(quantity),
        "order_quantity_source": source,
    }


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
            "eoq": _r(policy.eoq),
            **_level_dict(policy, result.order_quantity, result.order_quantity_source),
            **_dynamic_dict(result.levels, result.next_levels),
            **_period_stock_dict(result.safety_stocks, result.next_safety_stocks),
        },
        "simulation": _simulation_dict(sim),
        "notes": list(result.notes),
    }


def _dynamic_dict(levels: tuple[float, ...], next_levels: tuple[float, ...]) -> dict[str, Any]:
    if not levels and not next_levels:
        return {}
    return {"levels": _rs(levels), "next_levels": _rs(next_levels)}


def _period_stock_dict(stocks: tuple[float, ...], following: tuple[float, ...]) -> dict[str, Any]:
    if not stocks and not following:
        return {}
    return {"safety_stocks": _rs(stocks), "next_safety_stocks": _rs(following)}


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


def _replay_level_dict(replay: PolicyReplay, kind: str) -> dict[str, Any]:
    values: dict[str, Any]
    if kind == "RS":
        values = {"order_up_to": _r(replay.reorder_point), "reorder_point": None}
        values["order_quantity"] = None
    else:
        values = {
            "reorder_point": _r(replay.reorder_point),
            "order_quantity": _r(replay.order_quantity),
        }
        if kind == "RsS":
            values["order_up_to"] = _r(replay.reorder_point + replay.order_quantity)
    if replay.test_levels:
        values["test_levels"] = _rs(replay.test_levels)
    if replay.test_safety_stocks:
        values["test_safety_stocks"] = _rs(replay.test_safety_stocks)
    return values


def _rolling_policy_dict(replay: RollingReplay, kind: str) -> dict[str, Any]:
    values: dict[str, Any] = {
        "forecast_methods": list(replay.forecast_methods),
        "safety_stocks": _rs(replay.safety_stocks),
        ("order_up_to_levels" if kind == "RS" else "reorder_points"): _rs(replay.levels),
    }
    if kind != "RS":
        values["order_quantities"] = _rs(replay.order_quantities)
    values["out_of_sample"] = _simulation_dict(replay.out_of_sample)
    return values


def _rolling_dict(oos: OutOfSampleReport) -> dict[str, Any]:
    """The rolling-origin replay (ADR 0009); only present with the option."""
    from .validation import SAFETY_STOCK_METHODS

    if not oos.rolling_origin:
        return {}
    return {
        "rolling_origin": {
            "summary": {
                method: _totals_dict(oos.rolling_totals(method)) for method in SAFETY_STOCK_METHODS
            },
            "skus": [
                {
                    "sku": s.sku,
                    "policies": {r.method: _rolling_policy_dict(r, oos.policy) for r in s.rolling},
                }
                for s in oos.skus
            ],
        }
    }


def _cost_dict(cost: CostBreakdown) -> dict[str, Any]:
    return {
        "orders": cost.orders,
        "unit_periods": _r(cost.unit_periods),
        "units_short": _r(cost.units_short),
        "ordering": _r(cost.ordering),
        "holding": _r(cost.holding),
        "stockout": _r(cost.stockout),
        "total": _r(cost.total),
    }


def _origins(oos: OutOfSampleReport) -> tuple[str, ...]:
    return ("fixed", "rolling") if oos.rolling_origin else ("fixed",)


def _rates_dict(rates: CostRates) -> dict[str, Any]:
    return {"order": rates.order, "holding": rates.holding, "stockout": rates.stockout}


def _sku_rates_dict(oos: OutOfSampleReport, sku: str) -> dict[str, Any]:
    """A SKU's own rates (ADR 0014), only when some rate depends on the SKU."""
    if not oos.sku_rates:
        return {}
    rates = oos.sku_rates[sku]
    return {"rates": {k: _r(v) for k, v in _rates_dict(rates).items()}}


def _costs_dict(oos: OutOfSampleReport) -> dict[str, Any]:
    """The cost of the test periods (ADR 0012); only present with a cost rate."""
    from .validation import SAFETY_STOCK_METHODS

    if oos.costs is None:
        return {}
    origins = _origins(oos)
    rates = _rates_dict(oos.costs)
    if oos.holding_cost_rate is not None:
        rates["holding"] = None
        rates["holding_rate_of_unit_cost"] = oos.holding_cost_rate
    if oos.cost_columns:
        rates["cost_columns"] = True
    return {
        "costs": {
            "rates": rates,
            "summary": {
                method: {origin: _cost_dict(oos.cost(method, origin)) for origin in origins}
                for method in SAFETY_STOCK_METHODS
            },
            "skus": [
                {
                    "sku": s.sku,
                    **_sku_rates_dict(oos, s.sku),
                    "policies": {
                        method: {
                            origin: _cost_dict(oos.sku_cost(s, method, origin))
                            for origin in origins
                        }
                        for method in SAFETY_STOCK_METHODS
                    },
                }
                for s in oos.skus
            ],
        }
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
                        **_replay_level_dict(r, oos.policy),
                        "in_sample": _simulation_dict(r.in_sample),
                        "out_of_sample": _simulation_dict(r.out_of_sample),
                    }
                    for r in s.replays
                },
                "notes": list(s.notes),
            }
            for s in oos.skus
        ],
        **_rolling_dict(oos),
        **_costs_dict(oos),
        **_optimized_dict(oos),
    }


def _bootstrap_source_dict(config: Config) -> dict[str, Any]:
    """Settings of ADR 0008, only when used, so the default JSON stays that of 0.4.0."""
    if config.bootstrap_source == "demand":
        return {}
    return {
        "bootstrap_source": config.bootstrap_source,
        "period_safety_stock": config.period_safety_stock,
    }


def _rolling_setting(config: Config) -> dict[str, Any]:
    """Settings of ADRs 0009 and 0011, only when used, so the default JSON stays that of
    0.5.0 and the rolling origin's that of 0.6.0."""
    if not config.rolling_origin:
        return {}
    if config.refit_every == 1:
        return {"rolling_origin": True}
    return {"rolling_origin": True, "refit_every": config.refit_every}


def _cost_setting(config: Config) -> dict[str, Any]:
    """Settings of ADR 0012, only when a cost is set, so the default JSON stays that of 0.7.0."""
    if config.cost_rates is None:
        return {}
    settings: dict[str, Any] = {
        "order_cost": config.order_cost,
        "holding_cost": config.holding_cost,
        "stockout_cost": config.stockout_cost,
    }
    # ADR 0014, only when used, so the JSON with the shared rates stays that of 0.8.0.
    if config.holding_cost_rate is not None:
        settings["holding_cost_rate"] = config.holding_cost_rate
    if config.cost_columns:
        settings["cost_columns"] = True
    return settings


def _optimize_setting(config: Config) -> dict[str, Any]:
    """Settings of ADR 0015, only when used, so the JSON without them stays that of 0.8.0."""
    if not config.optimize_cost:
        return {}
    settings: dict[str, Any] = {"optimize_cost": True, "optimize_samples": config.optimize_samples}
    if config.optimize_fill_floor is not None:  # ADR 0016, only when set
        settings["optimize_fill_floor"] = config.optimize_fill_floor
    if config.optimize_paths != "forecast":  # ADR 0017, only when set
        settings["optimize_paths"] = config.optimize_paths
    return settings


def _optimized_dict(oos: OutOfSampleReport) -> dict[str, Any]:
    """The cost-optimised replay (ADR 0015); only present with the option."""
    from .optimize import COVER_PERIODS, SAFETY_Z

    if not oos.optimize_cost:
        return {}
    skus = []
    for s in oos.skus:
        assert s.optimized is not None  # every SKU is searched with the option
        found, search = s.optimized, s.optimized.search
        item: dict[str, Any] = {
            "sku": s.sku,
            "safety_stock": _r(search.safety_stock),
            "order_quantity": _r(search.order_quantity),
            "heuristic_safety_stock": _r(search.heuristic_safety_stock),
            "heuristic_order_quantity": _r(search.heuristic_order_quantity),
            "expected_cost": _r(search.expected_cost),
            "heuristic_expected_cost": _r(search.heuristic_cost),
            "candidates": search.candidates,
            "error_source": found.error_source,
            "errors": found.errors,
            "test_levels": _rs(found.test_levels),
            "out_of_sample": _simulation_dict(found.out_of_sample),
            "cost": _cost_dict(oos.optimized_sku_cost(s)),
        }
        if search.fill_floor is not None:  # ADR 0016
            item["expected_fill_rate"] = _r(search.expected_fill)
            item["heuristic_expected_fill_rate"] = _r(search.heuristic_fill)
            item["feasible"] = search.feasible
            item["fell_back"] = search.fell_back
        if oos.optimize_paths != "forecast":  # ADR 0017
            item["paths"] = found.paths
            item["refit_failures"] = found.refit_failures
        skus.append(item)
    searches = [s.optimized.search for s in oos.skus if s.optimized is not None]
    summary: dict[str, Any] = {
        "out_of_sample": _totals_dict(oos.optimized_totals()),
        "cost": _cost_dict(oos.optimized_cost()),
        "expected_cost": _r(sum(x.expected_cost for x in searches)),
        "heuristic_expected_cost": _r(sum(x.heuristic_cost for x in searches)),
    }
    optimized: dict[str, Any] = {
        "origin": "fixed",
        "samples": oos.optimize_samples,
        "grid": {"safety_z": list(SAFETY_Z), "cover_periods": list(COVER_PERIODS)},
    }
    if oos.optimize_fill_floor is not None:  # ADR 0016
        optimized["fill_floor"] = oos.optimize_fill_floor
        summary["fell_back"] = sum(x.fell_back for x in searches)
    if oos.optimize_paths != "forecast":  # ADR 0017
        from .optimize import block_length

        found_all = [s.optimized for s in oos.skus if s.optimized is not None]
        optimized["paths"] = {
            "kind": oos.optimize_paths,
            "refitted_skus": sum(x.paths == "refit" for x in found_all),
            "block_length": {
                s.sku: block_length(s.optimized.errors)
                for s in oos.skus
                if s.optimized is not None and s.optimized.paths == "refit"
            },
        }
    optimized["summary"] = summary
    optimized["skus"] = skus
    return {"optimized": optimized}


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
            "policy": config.policy,
            "dynamic_levels": config.dynamic_levels,
            **_bootstrap_source_dict(config),
            **_rolling_setting(config),
            **_cost_setting(config),
            **_optimize_setting(config),
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
                _method_label(method, oos),
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
    if oos.rolling_origin:
        lines += _rolling_lines(oos)
    if oos.costs is not None:
        lines += _cost_lines(oos)
    if oos.optimize_cost:
        lines += _optimized_lines(oos)
    return lines


def _cost_lines(oos: OutOfSampleReport) -> list[str]:
    from .validation import SAFETY_STOCK_METHODS

    assert oos.costs is not None  # only called with cost rates
    test = oos.test_calendar
    origins = _origins(oos)
    lines = [
        "",
        f"### Cost of the test periods ({test[0]} to {test[-1]})",
        "",
        f"Rates: {_rates_text(oos)}. The policies are the same as without costs; the "
        "cost only scores what each replay did in the test periods.",
        "",
    ]
    if oos.sku_rates:
        lines += _table(
            ["SKU", "Per order", "Per unit held a period", "Per unit short"],
            [
                [
                    s.sku,
                    _num(oos.sku_rates[s.sku].order, 2),
                    _num(oos.sku_rates[s.sku].holding, 4),
                    _num(oos.sku_rates[s.sku].stockout, 2),
                ]
                for s in oos.skus
            ],
        )
        lines += [""]
    rows = []
    for method in SAFETY_STOCK_METHODS:
        for origin in origins:
            cost = oos.cost(method, origin)
            rows.append(
                [
                    _method_label(method, oos),
                    origin,
                    str(cost.orders),
                    _num(cost.unit_periods),
                    _num(cost.units_short),
                    _num(cost.ordering),
                    _num(cost.holding),
                    _num(cost.stockout),
                    f"**{_num(cost.total)}**",
                ]
            )
    lines += _table(
        [
            "Safety stock",
            "Origin",
            "Orders",
            "Unit-periods held",
            "Units short",
            "Ordering",
            "Holding",
            "Stockout",
            "Total",
        ],
        rows,
    )
    lines += [""]
    sku_rows = []
    for s in oos.skus:
        for method in SAFETY_STOCK_METHODS:
            for origin in origins:
                cost = oos.sku_cost(s, method, origin)
                sku_rows.append(
                    [
                        s.sku,
                        _method_label(method, oos),
                        origin,
                        _num(cost.ordering),
                        _num(cost.holding),
                        _num(cost.stockout),
                        _num(cost.total),
                    ]
                )
    lines += _table(
        ["SKU", "Safety stock", "Origin", "Ordering", "Holding", "Stockout", "Total"], sku_rows
    )
    return lines


def _optimized_lines(oos: OutOfSampleReport) -> list[str]:
    from .validation import SAFETY_STOCK_METHODS

    test = oos.test_calendar
    quantity = "order quantity Q" if oos.policy == "sQ" else "order quantity Q (S = s + Q)"
    lines = [
        "",
        f"### Cost-optimised levels (fixed origin, test {test[0]} to {test[-1]})",
        "",
        f"Each SKU's safety stock and {quantity} are picked for the lowest expected cost "
        f"of the {len(test)} test periods, estimated on {oos.optimize_samples} demand paths "
        "built from the training periods only (the training forecast of each test period "
        "plus a one-step forecast error of training drawn at random). The level keeps the "
        "forecast part of the normal one. Grid: the normal safety stock or z x sigma for z "
        "from -1 to 3 by 0.25 (sigma: the training one-step errors x sqrt(L + R)); the "
        "heuristic quantity or 0.5 to 6 (by 0.5), 8, 10 or 12 periods of mean training "
        "demand; ties keep the heuristic. The test starts from the stock the normal policy "
        "left at the end of training, and the test demand is used only to score.",
        "",
    ]
    if oos.optimize_paths == "refit":  # ADR 0017
        lines[-1:-1] = ["", _refit_text(oos)]
    floor = oos.optimize_fill_floor
    if floor is not None:  # ADR 0016
        fell_back = sum(s.optimized.search.fell_back for s in oos.skus if s.optimized is not None)
        lines[-1:-1] = [
            "",
            f"Fill-rate floor: only pairs whose expected fill rate on the training paths is "
            f"at least {_pct(floor)} are accepted; a SKU with none keeps the heuristic pair "
            f"({fell_back} of {len(oos.skus)} SKU(s)).",
        ]
    rows = []
    for method in SAFETY_STOCK_METHODS:
        totals, cost = oos.totals(method, "out_of_sample"), oos.cost(method)
        rows.append(_optimized_row(_method_label(method, oos), totals, cost))
    rows.append(_optimized_row("cost-optimised", oos.optimized_totals(), oos.optimized_cost()))
    lines += _table(
        [
            "Policy",
            "Fill rate out",
            "Units short",
            "Avg on hand (sum)",
            "Orders",
            "Total cost of the test",
        ],
        rows,
    )
    if oos.rolling_origin:
        lines += ["", "The rolling origin is not searched: only the fixed origin is optimised."]
    lines += [""]
    sku_rows = []
    for s in oos.skus:
        assert s.optimized is not None  # every SKU is searched with the option
        search, normal = s.optimized.search, s.replay("normal")
        sku_rows.append(
            [
                s.sku,
                f"{_num(search.heuristic_safety_stock)} / {_num(search.safety_stock)}",
                f"{_num(search.heuristic_order_quantity)} / {_num(search.order_quantity)}",
                f"{_num(search.heuristic_cost)} / {_num(search.expected_cost)}",
                f"{_num(oos.sku_cost(s, 'normal').total)} / "
                f"{_num(oos.optimized_sku_cost(s).total)}",
                f"{_pct(normal.out_of_sample.fill_rate)} / "
                f"{_pct(s.optimized.out_of_sample.fill_rate)}",
            ]
        )
        if floor is not None:
            sku_rows[-1].insert(4, _fill_pair(search))
    headers = [
        "SKU",
        "Safety stock, normal / optimised",
        "Order qty, normal / optimised",
        "Expected cost on training paths, normal / optimised",
        "Test cost, normal / optimised",
        "Fill rate out, normal / optimised",
    ]
    if floor is not None:
        headers.insert(4, "Expected fill rate on training paths, normal / optimised")
    lines += _table(headers, sku_rows)
    return lines


def _refit_text(oos: OutOfSampleReport) -> str:
    """How the refit demand paths of ADR 0017 were built, and where they could not be."""
    found = [s.optimized for s in oos.skus if s.optimized is not None]
    refitted = [f for f in found if f.paths == "refit"]
    failures = sum(f.refit_failures for f in refitted)
    text = (
        "Refit paths: instead, each path rebuilds the training history as its one-step "
        "forecasts plus a moving-block bootstrap of their errors (blocks of about the cube "
        "root of the error count), refits the picked forecast method on it, and adds a "
        "resampled one-step error to that refit's forecast of each test period, so the "
        "paths also carry the uncertainty of the model's level, trend and season "
        f"({len(refitted)} of {len(found)} SKU(s) refitted"
    )
    if len(refitted) < len(found):
        text += "; the others had fewer than two one-step errors and keep the plain paths"
    if failures:
        text += f"; {failures} refit(s) without a valid fit kept the training forecast"
    return text + ")."


def _fill_pair(search: CostSearch) -> str:
    """Expected fill rates of the heuristic and picked pairs, marked when it fell back."""
    text = f"{_pct(search.heuristic_fill)} / {_pct(search.expected_fill)}"
    return text + " (none met the floor)" if search.fell_back else text


def _optimized_row(label: str, totals: ReplayTotals, cost: CostBreakdown) -> list[str]:
    return [
        label,
        _pct(totals.fill_rate),
        _num(cost.units_short),
        _num(totals.average_on_hand),
        str(cost.orders),
        f"**{_num(cost.total)}**",
    ]


def _rates_text(oos: OutOfSampleReport) -> str:
    """The rates sentence: the 0.8.0 wording with shared rates, the sources with per-SKU ones."""
    rates = oos.costs
    assert rates is not None  # only called with cost rates
    order = f"{rates.order:g} per order placed"
    stockout = f"{rates.stockout:g} per unit of demand not served from stock in its period"
    if oos.cost_columns:
        order += " (or the SKU's order_cost)"
        stockout += " (or the SKU's stockout_cost)"
    if oos.holding_cost_rate is None:
        holding = f"{rates.holding:g} per unit on hand at the end of a period"
    else:
        holding = (
            f"{oos.holding_cost_rate:g} a year of the SKU's unit_cost per unit on hand at "
            "the end of a period (that rate x unit_cost / periods per year, each period)"
        )
    text = f"{order}, {holding}, {stockout} (backordered)"
    if oos.sku_rates:
        text += "; each SKU's rates are in the first table"
    return text


def _picks(methods: tuple[str, ...]) -> str:
    """``naive x 8, ses x 4``: the forecasts picked at the origins, in order of first pick."""
    counts: dict[str, int] = {}
    for method in methods:
        counts[method] = counts.get(method, 0) + 1
    return ", ".join(f"{method} x {count}" for method, count in counts.items())


def _rolling_lines(oos: OutOfSampleReport) -> list[str]:
    from .validation import SAFETY_STOCK_METHODS

    test = oos.test_calendar
    every = oos.refit_every
    when = (
        "At the start of every test period"
        if every == 1
        else f"At the start of the first test period and then every {every} test periods"
    )
    keep = (
        ""
        if every == 1
        else f" Each refit decides its own period and the next {every - 1} (its forecasts "
        f"1 to {every} steps ahead with dynamic levels)."
    )
    lines = [
        "",
        f"### Rolling origin (test {test[0]} to {test[-1]})",
        "",
        f"{when} each SKU is refitted on the periods before it "
        "only (training plus the test periods already observed): classes, forecast pick, "
        "sigma, lead times, bootstrap draws, safety stock, level and order quantity."
        f"{keep} Both "
        "replays enter the test from the same stock; the fixed origin keeps the policy "
        "fitted at the end of training.",
        "",
    ]
    rows = []
    for method in SAFETY_STOCK_METHODS:
        fixed, rolling = oos.totals(method, "out_of_sample"), oos.rolling_totals(method)
        rows.append(
            [
                _method_label(method, oos),
                f"{_pct(fixed.fill_rate)} / {_pct(rolling.fill_rate)}",
                f"{fixed.stockout_periods} / {rolling.stockout_periods}",
                f"{_num(fixed.average_on_hand)} / {_num(rolling.average_on_hand)}",
            ]
        )
    lines += _table(
        [
            "Safety stock",
            "Fill rate out, fixed / rolling",
            "Stockout periods out, fixed / rolling",
            "Avg on hand out (sum), fixed / rolling",
        ],
        rows,
    )
    lines += [""]
    sku_rows = []
    for s in oos.skus:
        cells = [s.sku, _picks(s.rolling_replay("normal").forecast_methods)]
        for method in SAFETY_STOCK_METHODS:
            fixed_rate = s.replay(method).out_of_sample.fill_rate
            rolling_rate = s.rolling_replay(method).out_of_sample.fill_rate
            cells.append(f"{_pct(fixed_rate)} / {_pct(rolling_rate)}")
        sku_rows.append(cells)
    lines += _table(
        [
            "SKU",
            "Forecasts picked at the origins",
            "Fill rate normal, fixed / rolling",
            "Fill rate bootstrap, fixed / rolling",
        ],
        sku_rows,
    )
    return lines


def _method_label(method: str, oos: OutOfSampleReport) -> str:
    if method == "bootstrap" and oos.bootstrap_source == "residuals":
        return "bootstrap (forecast residuals)"
    return method


def _safety_stock_cell(result: SkuResult) -> str:
    stock = _num(result.policy.safety_stock)
    if not result.next_safety_stocks:
        return stock
    low, high = min(result.next_safety_stocks), max(result.next_safety_stocks)
    return f"{stock} ({_num(low)} to {_num(high)})"


LEVEL_HEADERS = {
    "sQ": ("Reorder point (s)", "Order qty (Q)"),
    "RS": ("Order-up-to (S)", "Review (R)"),
    "RsS": ("Reorder level (s)", "Order qty (Q = S - s)", "Review (R)"),
}


def _level_cells(result: SkuResult, kind: str) -> list[str]:
    """The cells under :data:`LEVEL_HEADERS` of one SKU."""
    review = f"{result.policy.review_period:g}"
    quantity = f"{_num(result.order_quantity)} ({result.order_quantity_source})"
    if kind == "RS":
        return [_level_cell(result), review]
    if kind == "RsS":
        return [_level_cell(result), quantity, review]
    return [_level_cell(result), quantity]


def _level_cell(result: SkuResult) -> str:
    level = _num(result.policy.reorder_point)
    if not result.next_levels:
        return level
    low, high = min(result.next_levels), max(result.next_levels)
    return f"{level} ({_num(low)} to {_num(high)})"


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
    if config.policy != "sQ" or config.dynamic_levels:
        lines.append(_policy_label(config))
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
            *LEVEL_HEADERS[config.policy],
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
                _safety_stock_cell(r),
                *_level_cells(r, config.policy),
                _pct(r.simulation.fill_rate),
                f"{r.simulation.stockout_periods}/{r.simulation.periods}",
                _num(r.simulation.average_on_hand),
            ]
            for r in report.skus
        ],
    )
    if config.dynamic_levels:
        lines += [
            "",
            "With dynamic levels the level column shows the level at the end of the "
            "history and, in parentheses, the lowest and highest level of the next "
            f"{len(report.skus[0].next_levels)} period(s); the JSON report lists every one.",
        ]
        if any(r.next_safety_stocks for r in report.skus):
            lines[-1] += (
                " A safety stock per period is shown the same way: at the end of the history "
                "and, in parentheses, its range over those periods."
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
        f"history under the {_policy_name(config)} policy (in-sample): a check of the "
        "formulas on the data, not a forecast of future service.",
        "",
    ]
    return "\n".join(lines)
