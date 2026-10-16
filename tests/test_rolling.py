"""Rolling-origin out-of-sample replay (ADR 0009): by hand, no leak, wiring, results."""

from __future__ import annotations

import json
from dataclasses import replace
from functools import cache
from typing import Any

import pytest
from conftest import EXAMPLES
from test_smoothing import integer, monthly, trend_seasonal_series

from inventory_policy_lab import (
    Config,
    ConfigError,
    OutOfSampleReport,
    analyze,
    analyze_file,
    render_json,
    render_markdown,
    simulate,
)
from inventory_policy_lab import analysis as analysis_module
from inventory_policy_lab.cli import main
from inventory_policy_lab.reader import SkuHistory

SYNTHETIC = EXAMPLES / "demand_synthetic.csv"
HAND = {"A": [10.0, 10.0, 10.0, 10.0, 20.0, 30.0, 30.0]}
HAND_CONFIG = Config(test_periods=3, holdout=2, lead_time=0, rolling_origin=True)


# --- the simulator with one order quantity per period --------------------------------


def test_simulate_with_a_quantity_per_period_by_hand() -> None:
    # s = 5 every period, L = 0; the run starts with s + Q(0) = 5 + 10 = 15 on hand.
    # t = 0: serve 5 -> 10, position 10 > 5, no order.
    # t = 1: serve 5 -> 5, position 5 <= 5: order Q(1) = 3 -> 8 > 5 (one order, due t = 2).
    # t = 2: receive 3 -> 8, serve 5 -> 3; order Q(2) = 1 three times: 4, 5, 6 (due t = 3).
    result = simulate([5, 5, 5], 5, [10, 3, 1], lead_time=0)
    assert (result.orders_placed, result.served_from_stock) == (4, 15)
    assert result.average_on_hand == pytest.approx((10 + 5 + 3) / 3)
    # One quantity for every period is the scalar replay.
    assert simulate([5, 5, 5], 5, [10, 10, 10], 0) == simulate([5, 5, 5], 5, 10, 0)
    with pytest.raises(ValueError, match="order_quantity must be positive"):
        simulate([5, 5], 5, [10, 0], 0)
    with pytest.raises(ValueError, match="one level per period: 1 for 2"):
        simulate([5, 5], 5, [10], 0)


# --- the rolling replay, by hand -----------------------------------------------------


def test_rolling_origin_by_hand() -> None:
    """One SKU, holdout 2, L = 0, R = 1 (protection 1 period), service 95%, z = 1.644854.

    Train: 10 10 10 10. Test: 20 30 30. Naive, moving average and SES forecast 10
    on a flat history, and the naive MAE scale of the training part is 0 at each
    origin below, so MASE is undefined and the pick is by MAE (ties: naive first).

    Origin 4 (sees 10 10 10 10), the fixed policy: forecast 10, sigma 0, SS 0,
      s = 10, Q = 10.
    Origin 5 (sees 10 10 10 10 20): holdout errors at 3 and 4 are 0 and 10 for all
      three methods; naive wins the tie. Forecast 20, sigma = stdev = sqrt(20) =
      4.4721, SS = 1.644854 x 4.4721 = 7.3560, s = 27.3560, Q = 20.
    Origin 6 (sees ... 20 30): errors at 4 and 5: naive 10 and 10 (MAE 10), moving
      average 10 and 16.67, SES 10 and 18 (level 12). Naive: forecast 30, sigma =
      sqrt(70) = 8.3666, SS = 13.7618, s = 43.7618, Q = 30.

    Training replay (s = 10, Q = 10, L = 0) starts with 20, ends with 10 on hand
    and 10 due at period 4. Test:
      fixed:   t4: 20, serve 20 -> 0, order 10 + 10. t5: 20, serve 30 -> -10 (out),
               order 3 x 10. t6: 20, serve 30 -> -10 (out). Served 20 + 20 + 20 = 60
               of 80: 75%, 2 stockout periods.
      rolling: t4 as fixed. t5: 20, serve 30 -> -10 (out); s = 27.36, Q = 20: orders
               to 10, 30 (two). t6: 30, serve 30 -> 0. Served 70 of 80: 87.5%, 1.
    The bootstrap of one period: the 95% quantile of 10 10 10 10 20 is 20 and of
    ... 20 30 is 30, each equal to the forecast, so its safety stock is 0 at every
    origin and its levels are the forecasts.
    """
    oos = analyze(integer(HAND), HAND_CONFIG).out_of_sample
    assert oos is not None and oos.rolling_origin
    (sku,) = oos.skus
    normal = sku.rolling_replay("normal")
    assert normal.forecast_methods == ("naive", "naive", "naive")
    assert normal.levels == pytest.approx((10, 27.3560, 43.7618), abs=1e-4)
    assert normal.safety_stocks == pytest.approx((0, 7.3560, 13.7618), abs=1e-4)
    assert normal.order_quantities == (10, 20, 30)
    result = normal.out_of_sample
    assert (result.fill_rate, result.stockout_periods, result.average_on_hand) == (0.875, 1, 0)
    fixed = sku.replay("normal").out_of_sample
    assert (fixed.fill_rate, fixed.stockout_periods) == (0.75, 2)
    boot = sku.rolling_replay("bootstrap")
    assert (boot.safety_stocks, boot.levels) == ((0, 0, 0), (10, 20, 30))
    assert boot.out_of_sample.fill_rate == 0.875
    assert oos.rolling_totals("normal").fill_rate == 0.875


def test_first_origin_is_the_fixed_policy() -> None:
    """The first test period is decided from the training periods in both replays."""
    for settings in (
        {},
        {"policy": "RS", "dynamic_levels": True},
        {
            "policy": "RS",
            "dynamic_levels": True,
            "bootstrap_source": "residuals",
            "period_safety_stock": True,
        },
    ):
        config = Config(test_periods=12, trend_seasonal=True, rolling_origin=True, **settings)  # type: ignore[arg-type]
        oos = analyze_file(SYNTHETIC, config).out_of_sample
        assert oos is not None
        for s in oos.skus:
            for fixed, rolling in zip(s.replays, s.rolling, strict=True):
                assert fixed.method == rolling.method
                assert rolling.forecast_methods[0] == s.forecast_method
                assert rolling.order_quantities[0] == fixed.order_quantity
                first_level = fixed.test_levels[0] if fixed.test_levels else fixed.reorder_point
                assert rolling.levels[0] == pytest.approx(first_level)
                stocks = fixed.test_safety_stocks
                assert rolling.safety_stocks[0] == pytest.approx(
                    stocks[0] if stocks else fixed.safety_stock
                )
                assert len(rolling.levels) == len(rolling.safety_stocks) == 12
    # With a safety stock per period, a damped Holt pick moves it from origin to origin.
    assert oos is not None
    item = next(x for x in oos.skus if x.sku == "SKU-003").rolling_replay("bootstrap")
    assert "holt_damped" in item.forecast_methods
    assert len(set(item.safety_stocks)) > 1


# --- no leak ------------------------------------------------------------------------


def test_refits_never_see_the_period_they_decide(monkeypatch: pytest.MonkeyPatch) -> None:
    # The last test period is a sentinel: no refit may see it, and the origins see
    # 4, 5 and 6 periods in turn.
    real = analysis_module._analyze_sku
    seen: list[tuple[int, int | None]] = []

    def recording(history: SkuHistory, config: Config, *args: Any, **kwargs: Any) -> Any:
        if "horizon" in kwargs:  # an out-of-sample fit, fixed or rolling
            assert 999 not in history.demand
            seen.append((len(history.demand), kwargs["horizon"]))
        return real(history, config, *args, **kwargs)

    monkeypatch.setattr(analysis_module, "_analyze_sku", recording)
    data = integer({"A": [10.0, 10.0, 10.0, 10.0, 20.0, 30.0, 999.0]})
    analyze(data, HAND_CONFIG)
    # Per method: the fixed fit on train (horizon 3), then the three origins.
    assert seen == [(4, 3), (4, 1), (5, 1), (6, 1)] * 2


@cache
def _series_report(cut: int | None = None) -> OutOfSampleReport:
    """The 48-month series (36 train, 12 test), (R, S) dynamic, residual bootstrap.

    With ``cut``, every period from that index on is replaced by zero demand.
    """
    series = trend_seasonal_series()
    if cut is not None:
        series = {sku: values[:cut] + [0.0] * (48 - cut) for sku, values in series.items()}
    config = Config(
        test_periods=12,
        trend_seasonal=True,
        policy="RS",
        dynamic_levels=True,
        bootstrap_source="residuals",
        rolling_origin=True,
    )
    oos = analyze(monthly(series), config).out_of_sample
    assert oos is not None
    return oos


def test_no_leak_from_later_test_periods_into_earlier_decisions() -> None:
    # Periods 40 to 47 become zero. Origins 36 to 40 (test periods 0 to 4) see
    # only periods before 40, so their decisions must not move; later ones may.
    base, other = _series_report(), _series_report(40)
    kept = 40 - 36 + 1
    moved = False
    for a, b in zip(base.skus, other.skus, strict=True):
        for ra, rb in zip(a.replays, b.replays, strict=True):
            assert (ra.reorder_point, ra.test_levels, ra.in_sample) == (
                rb.reorder_point,
                rb.test_levels,
                rb.in_sample,
            )
        for qa, qb in zip(a.rolling, b.rolling, strict=True):
            assert qa.forecast_methods[:kept] == qb.forecast_methods[:kept]
            assert qa.levels[:kept] == qb.levels[:kept]
            assert qa.safety_stocks[:kept] == qb.safety_stocks[:kept]
            assert qa.order_quantities[:kept] == qb.order_quantities[:kept]
            moved = moved or qa.levels[kept:] != qb.levels[kept:]
    assert moved  # the later origins did see the change: the test has teeth


# --- options, rendering and command line ---------------------------------------------


def test_rolling_origin_needs_test_periods() -> None:
    with pytest.raises(ConfigError, match="needs test periods"):
        Config(rolling_origin=True).validate()


def test_markdown_and_json_with_a_rolling_origin() -> None:
    report = analyze(integer(HAND), HAND_CONFIG)
    text = render_markdown(report)
    assert "### Rolling origin (test 5 to 7)" in text
    assert "| normal | 75.0% / 87.5% | 2 / 1 | 0.0 / 0.0 |" in text
    assert "| A | naive x 3 | 75.0% / 87.5% | 75.0% / 87.5% |" in text
    data = json.loads(render_json(report))
    assert data["settings"]["rolling_origin"] is True
    rolling = data["out_of_sample"]["rolling_origin"]
    assert rolling["summary"]["normal"]["fill_rate"] == 0.875
    policy = rolling["skus"][0]["policies"]["normal"]
    assert policy["reorder_points"] == [10.0, 27.356, 43.7618]
    assert policy["order_quantities"] == [10.0, 20.0, 30.0]
    assert policy["forecast_methods"] == ["naive"] * 3
    assert policy["out_of_sample"]["stockout_periods"] == 1

    rs = analyze(integer(HAND), replace(HAND_CONFIG, policy="RS"))
    policy = json.loads(render_json(rs))["out_of_sample"]["rolling_origin"]["skus"][0]
    assert "order_quantities" not in policy["policies"]["normal"]
    assert len(policy["policies"]["normal"]["order_up_to_levels"]) == 3


def test_default_reports_have_no_rolling_keys() -> None:
    report = analyze(integer(HAND), Config(test_periods=3, holdout=2, lead_time=0))
    data = json.loads(render_json(report))
    assert "rolling_origin" not in data["settings"]
    assert "rolling_origin" not in data["out_of_sample"]
    assert "Rolling origin" not in render_markdown(report)
    assert report.out_of_sample is not None
    assert all(s.rolling == () for s in report.out_of_sample.skus)


def test_cli_option(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(SYNTHETIC), "--rolling-origin"]) == 2
    assert "needs test periods" in capsys.readouterr().err
    assert main([str(SYNTHETIC), "--test-periods", "12", "--rolling-origin"]) == 0
    out = capsys.readouterr().out
    assert "| normal | 94.4% / 99.8% | 11 / 4 | 885.2 / 919.1 |" in out


# --- results quoted in the README and ADR 0009 ---------------------------------------


def _fixed_and_rolling(oos: OutOfSampleReport) -> dict[str, tuple[tuple[float, int, float], ...]]:
    """(fill rate, stockout periods, avg on hand summed), fixed then rolling, per method."""
    return {
        method: tuple(
            (round(t.fill_rate or 0, 3), t.stockout_periods, round(t.average_on_hand, 1))
            for t in (oos.totals(method, "out_of_sample"), oos.rolling_totals(method))
        )
        for method in ("normal", "bootstrap")
    }


def _residual_config(**settings: Any) -> Config:
    return Config(
        test_periods=12,
        trend_seasonal=True,
        bootstrap_source="residuals",
        rolling_origin=True,
        **settings,
    )


def test_48_month_series_results_quoted_in_the_readme() -> None:
    sq_oos = analyze(monthly(trend_seasonal_series()), _residual_config()).out_of_sample
    assert sq_oos is not None
    assert _fixed_and_rolling(sq_oos) == {
        "normal": ((0.996, 1, 289.0), (1.0, 0, 321.6)),
        "bootstrap": ((0.984, 3, 185.5), (0.996, 1, 220.9)),
    }
    assert _fixed_and_rolling(_series_report()) == {
        "normal": ((1.0, 0, 105.5), (1.0, 0, 149.3)),
        "bootstrap": ((0.954, 18, 13.1), (0.994, 4, 36.4)),
    }
    picks = {s.sku: s.rolling_replay("normal").forecast_methods for s in _series_report().skus}
    assert picks["TS"] == ("hw_multiplicative",) * 12
    assert picks["T"][:3] == ("naive", "naive", "holt_damped")
    t = next(s for s in _series_report().skus if s.sku == "T").rolling_replay("bootstrap")
    assert (round(min(t.safety_stocks), 1), round(max(t.safety_stocks), 1)) == (13.6, 36.6)
    assert t.out_of_sample.stockout_periods == 0


def test_synthetic_example_results_quoted_in_the_readme() -> None:
    sq = analyze_file(SYNTHETIC, _residual_config()).out_of_sample
    rs = analyze_file(SYNTHETIC, _residual_config(policy="RS", dynamic_levels=True)).out_of_sample
    assert sq is not None and rs is not None
    assert {"sQ": _fixed_and_rolling(sq), "RS": _fixed_and_rolling(rs)} == {
        "sQ": {
            "normal": ((0.944, 11, 885.2), (0.998, 4, 932.4)),
            "bootstrap": ((0.922, 15, 975.8), (0.985, 9, 913.7)),
        },
        "RS": {
            "normal": ((0.909, 20, 598.6), (0.973, 10, 627.5)),
            "bootstrap": ((0.885, 23, 690.9), (0.96, 14, 678.2)),
        },
    }
