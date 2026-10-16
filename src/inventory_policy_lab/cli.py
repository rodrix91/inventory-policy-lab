"""Command-line interface: ``inventory-policy-lab demand.csv [options]``."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .analysis import Config, analyze_file
from .errors import EXIT_INPUT, EXIT_OK, InventoryPolicyError
from .render import render_json, render_markdown

EXIT_CODES_HELP = """exit codes:
  0  report written
  2  invalid option or option value
  3  input file missing, unreadable or not UTF-8
  4  invalid data (missing column, bad number, mixed period formats)
  5  history too short for the holdout (or for --test-periods)"""


def _pair(text: str) -> tuple[float, float]:
    parts = text.split(",")
    try:
        if len(parts) != 2:
            raise ValueError
        return float(parts[0]), float(parts[1])
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"expected two numbers like 0.8,0.95, got {text!r}"
        ) from None


def _class_levels(text: str) -> dict[str, float]:
    levels: dict[str, float] = {}
    for item in text.split(","):
        name, sep, value = item.partition("=")
        try:
            if not sep:
                raise ValueError
            levels[name.strip().upper()] = float(value)
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"expected CLASS=LEVEL pairs like A=0.99,B=0.95, got {text!r}"
            ) from None
    return levels


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="inventory-policy-lab",
        description=(
            "Turn a CSV of demand history per SKU into an inventory-policy report: "
            "ABC-XYZ, demand patterns, backtested forecasts, safety stock, reorder "
            "point, EOQ and a replay of the policy on the history."
        ),
        epilog=EXIT_CODES_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add = parser.add_argument
    add("path", type=Path, help="CSV with columns sku, period, quantity[, unit_cost, lead_time]")
    add("--format", choices=("markdown", "json"), default="markdown", help="output format")
    add("-o", "--output", type=Path, help="write the report to this file instead of stdout")
    add("--version", action="version", version=f"%(prog)s {__version__}")

    group = parser.add_argument_group("service and policy")
    group.add_argument(
        "--service-level", type=float, default=0.95, help="target cycle service level (0.95)"
    )
    group.add_argument(
        "--class-service-levels",
        type=_class_levels,
        default={},
        metavar="A=0.99,B=0.95,C=0.9",
        help="service level per ABC class, overriding --service-level",
    )
    group.add_argument(
        "--lead-time",
        type=float,
        default=1.0,
        help="lead time in periods for SKUs without lead_time values (1)",
    )
    group.add_argument(
        "--lead-time-std",
        type=float,
        default=0.0,
        help="standard deviation of that default lead time (0)",
    )
    group.add_argument(
        "--review-period",
        type=float,
        default=1.0,
        help=(
            "periods between inventory reviews, added to the protection interval; "
            "a whole number of at least 1 with --policy RS or RsS (1)"
        ),
    )
    group.add_argument(
        "--policy",
        choices=("sQ", "RS", "RsS"),
        default="sQ",
        help=(
            "sQ: reorder point s and fixed quantity Q, checked every period; RS: periodic "
            "review every R periods, ordering up to S; RsS: periodic review every R periods, "
            "ordering up to S = s + Q only when the position is at or below s (sQ)"
        ),
    )
    group.add_argument(
        "--dynamic-levels",
        action="store_true",
        help=(
            "let s or S follow a trend or seasonal forecast period by period instead of one "
            "level for the whole year (needs --trend-seasonal)"
        ),
    )
    group.add_argument(
        "--ordering-cost", type=float, help="cost per order, for EOQ (needs --holding-rate)"
    )
    group.add_argument(
        "--holding-rate",
        type=float,
        help="yearly holding cost as a fraction of unit cost, for EOQ (e.g. 0.25)",
    )
    group.add_argument(
        "--order-cover",
        type=float,
        default=1.0,
        help="without EOQ, order quantity = forecast x this many periods (1)",
    )
    group.add_argument(
        "--sigma",
        choices=("demand", "rmse"),
        default="demand",
        help="safety-stock sigma: demand std dev, or RMSE of the picked forecast (demand)",
    )
    group.add_argument(
        "--safety-stock",
        choices=("normal", "bootstrap"),
        default="normal",
        help="normal formula, or bootstrap quantile of protection-interval demand (normal)",
    )
    group.add_argument(
        "--bootstrap-source",
        choices=("demand", "residuals"),
        default="demand",
        help=(
            "what the bootstrap resamples: demand per period, or the rolling-origin errors "
            "of the picked forecast over the protection interval; applies to "
            "--safety-stock bootstrap and to the bootstrap replay of --test-periods (demand)"
        ),
    )
    group.add_argument(
        "--period-safety-stock",
        action="store_true",
        help=(
            "with --dynamic-levels and --bootstrap-source residuals, give each period its own "
            "safety stock, proportional to the forecast it protects"
        ),
    )
    group.add_argument(
        "--bootstrap-samples",
        type=int,
        default=2000,
        help="draws per SKU with --safety-stock bootstrap, at least 100 (2000)",
    )
    group.add_argument("--seed", type=int, default=0, help="random seed of the bootstrap (0)")
    group.add_argument(
        "--test-periods",
        type=int,
        default=0,
        metavar="N",
        help=(
            "also fit normal and bootstrap policies on all but the last N periods and "
            "replay them out of sample on those N (0: off)"
        ),
    )
    group.add_argument(
        "--rolling-origin",
        action="store_true",
        help=(
            "with --test-periods, also replay the test window refitting forecast, safety "
            "stock and levels at the start of every test period from the periods before it"
        ),
    )
    group.add_argument(
        "--refit-every",
        type=int,
        default=1,
        metavar="K",
        help=(
            "with --rolling-origin, refit only at the start of every K-th test period and "
            "keep that refit's decisions (its forecasts 1 to K steps ahead) until the "
            "next (1: every period)"
        ),
    )

    group = parser.add_argument_group(
        "cost of the out-of-sample replay",
        "with --test-periods, score every replay of the test periods in money; a cost left "
        "out counts as 0 once another is given; the policy itself does not change",
    )
    group.add_argument("--order-cost", type=float, metavar="C", help="cost per order placed")
    group.add_argument(
        "--holding-cost",
        type=float,
        metavar="C",
        help="cost per unit on hand at the end of a period, per period",
    )
    group.add_argument(
        "--stockout-cost",
        type=float,
        metavar="C",
        help="cost per unit of demand not served from stock in its period (backordered)",
    )
    group.add_argument(
        "--holding-cost-rate",
        type=float,
        metavar="RATE",
        help=(
            "instead of --holding-cost: yearly holding cost as a fraction of each SKU's "
            "unit_cost (e.g. 0.25), so a unit held one period costs RATE x unit_cost / "
            "--periods-per-year; needs a unit_cost column"
        ),
    )
    group.add_argument(
        "--cost-columns",
        action="store_true",
        help=(
            "read a cost per order and per unit short of each SKU from the optional "
            "order_cost and stockout_cost columns (most recent non-empty value); a SKU "
            "without a value uses --order-cost and --stockout-cost"
        ),
    )

    group = parser.add_argument_group(
        "cost-optimised levels",
        "with cost rates and --policy sQ or RsS, also pick each SKU's safety stock and order "
        "quantity for the lowest expected cost of the test window, estimated on demand paths "
        "built from the training periods only, and replay that policy on the test (fixed "
        "origin)",
    )
    group.add_argument(
        "--optimize-cost",
        action="store_true",
        help="search s and Q (S = s + Q for RsS) on a bounded grid; see ADR 0015",
    )
    group.add_argument(
        "--optimize-samples",
        type=int,
        default=100,
        metavar="N",
        help="demand paths per SKU of that search, at least 10 (100)",
    )
    group.add_argument(
        "--optimize-fill-floor",
        type=float,
        default=None,
        metavar="F",
        help=(
            "accept only pairs whose expected fill rate on the training paths is at least "
            "F, in (0, 1]; without one, keep the heuristic pair; see ADR 0016 (off)"
        ),
    )

    group.add_argument(
        "--optimize-paths",
        choices=("forecast", "refit"),
        default="forecast",
        help=(
            "demand paths of that search: the training forecast plus resampled errors "
            "(forecast), or a forecast refitted on each block-bootstrapped training "
            "history, which adds the model's own uncertainty (refit); see ADR 0017 (forecast)"
        ),
    )

    group = parser.add_argument_group("classification and forecasting")
    group.add_argument(
        "--abc-thresholds", type=_pair, default=(0.8, 0.95), help="cumulative shares (0.8,0.95)"
    )
    group.add_argument(
        "--xyz-thresholds", type=_pair, default=(0.5, 1.0), help="CV limits of X and Y (0.5,1.0)"
    )
    group.add_argument(
        "--periods-per-year", type=float, default=12.0, help="to annualize demand (12)"
    )
    group.add_argument(
        "--holdout", type=int, default=6, help="periods held out for the backtest (6)"
    )
    group.add_argument(
        "--trend-seasonal",
        action="store_true",
        help=(
            "also backtest damped Holt and Holt-Winters (additive, multiplicative) on smooth "
            "and erratic SKUs when the history allows"
        ),
    )
    group.add_argument(
        "--season-length",
        type=int,
        metavar="M",
        help="season of Holt-Winters in periods (default: --periods-per-year, 12)",
    )
    group.add_argument("--ma-window", type=int, default=3, help="moving-average window (3)")
    group.add_argument("--ses-alpha", type=float, default=0.2, help="SES smoothing (0.2)")
    group.add_argument(
        "--croston-alpha", type=float, default=0.1, help="Croston/SBA smoothing (0.1)"
    )
    return parser


def config_from_args(args: argparse.Namespace) -> Config:
    return Config(
        service_level=args.service_level,
        class_service_levels=args.class_service_levels,
        holdout=args.holdout,
        ma_window=args.ma_window,
        ses_alpha=args.ses_alpha,
        croston_alpha=args.croston_alpha,
        periods_per_year=args.periods_per_year,
        abc_thresholds=args.abc_thresholds,
        xyz_thresholds=args.xyz_thresholds,
        lead_time=args.lead_time,
        lead_time_std=args.lead_time_std,
        review_period=args.review_period,
        ordering_cost=args.ordering_cost,
        holding_rate=args.holding_rate,
        order_cover=args.order_cover,
        sigma=args.sigma,
        safety_stock_method=args.safety_stock,
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
        test_periods=args.test_periods,
        trend_seasonal=args.trend_seasonal,
        season_length=args.season_length,
        policy=args.policy,
        dynamic_levels=args.dynamic_levels,
        bootstrap_source=args.bootstrap_source,
        period_safety_stock=args.period_safety_stock,
        rolling_origin=args.rolling_origin,
        refit_every=args.refit_every,
        order_cost=args.order_cost,
        holding_cost=args.holding_cost,
        stockout_cost=args.stockout_cost,
        holding_cost_rate=args.holding_cost_rate,
        cost_columns=args.cost_columns,
        optimize_cost=args.optimize_cost,
        optimize_samples=args.optimize_samples,
        optimize_fill_floor=args.optimize_fill_floor,
        optimize_paths=args.optimize_paths,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = analyze_file(args.path, config_from_args(args))
    except InventoryPolicyError as exc:
        print(f"inventory-policy-lab: error: {exc}", file=sys.stderr)
        return exc.exit_code
    text = render_json(report) if args.format == "json" else render_markdown(report)
    if args.output is None:
        sys.stdout.write(text)
        return EXIT_OK
    try:
        args.output.write_text(text, encoding="utf-8")
    except OSError as exc:
        print(f"inventory-policy-lab: error: cannot write {args.output}: {exc}", file=sys.stderr)
        return EXIT_INPUT
    return EXIT_OK
