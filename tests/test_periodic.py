"""Periodic review (R, S) and dynamic levels: numbers by hand, no leak, wiring and results."""

from __future__ import annotations

import json

import pytest
from conftest import EXAMPLES
from test_smoothing import monthly, trend_seasonal_series

from inventory_policy_lab import (
    Config,
    ConfigError,
    analyze,
    analyze_file,
    build_policy,
    dynamic_levels,
    parse_rows,
    render_json,
    render_markdown,
    replay_policy,
    simulate,
    simulate_periodic,
)
from inventory_policy_lab.smoothing import SmoothingFit

WORKED = EXAMPLES / "worked_example.csv"
SYNTHETIC = EXAMPLES / "demand_synthetic.csv"


# --- the replay, by hand -------------------------------------------------------------


def test_periodic_replay_by_hand() -> None:
    # S = 12, R = 2, L = 1: reviews at the end of t1, t3, t5; an order arrives at t + 2.
    # t0: 12 on hand, demand 4 -> 8.                         no review
    # t1: demand 6 -> 2.            review: position 2,  order 10 (due t3)
    # t2: serve 2 of 5 (stockout) -> net -3.                 no review
    # t3: +10 -> 7, demand 3 -> 4.  review: position 4,  order 8 (due t5)
    # t4: serve 4 of 7 (stockout) -> net -3.                 no review
    # t5: +8 -> 5, demand 5 -> 0.   review: position 0,  order 12 (due t7)
    result = simulate_periodic([4, 6, 5, 3, 7, 5], order_up_to=12, review_period=2, lead_time=1)
    assert result.total_demand == 30
    assert result.served_from_stock == 24
    assert result.fill_rate == pytest.approx(0.8)
    assert result.stockout_periods == 2
    assert result.average_on_hand == pytest.approx((8 + 2 + 0 + 4 + 0 + 0) / 6)
    assert result.orders_placed == 3
    assert result.max_backorder == 3
    assert result.lead_time_periods == 1


def test_periodic_replay_with_levels_and_warmup() -> None:
    # R = 1, L = 0, levels 10 10 20 20, the first two periods not scored.
    # t0: 10 on hand, demand 5 -> 5.  position 5 < 10:  order 5 (due t1), not scored
    # t1: +5 -> 10, demand 5 -> 5.    position 5 < 10:  order 5 (due t2), not scored
    # t2: +5 -> 10, demand 5 -> 5.    position 5 < 20:  order 15 (due t3)
    # t3: +15 -> 20, demand 5 -> 15.  position 15 < 20: order 5
    result = simulate_periodic(
        [5, 5, 5, 5], [10, 10, 20, 20], review_period=1, lead_time=0, warmup=2
    )
    assert (result.periods, result.total_demand, result.served_from_stock) == (2, 10, 10)
    assert result.average_on_hand == pytest.approx((5 + 15) / 2)
    assert result.orders_placed == 2
    assert result.stockout_periods == 0


def test_no_order_when_the_position_is_at_or_above_s() -> None:
    result = simulate_periodic([0, 0, 3], order_up_to=5, review_period=1, lead_time=0)
    assert result.orders_placed == 1  # only after the demand of t2
    assert simulate_periodic([], 5, 1, 1).average_on_hand == 0
    assert simulate_periodic([], [], 1, 1).periods == 0


def test_sq_replay_with_a_reorder_point_per_period() -> None:
    # Q = 10, L = 0, s = 4, 12, 0. Starts with s(0) + Q = 14 on hand.
    # t0: demand 5 -> 9.            position 9 > 4
    # t1: demand 5 -> 4.            position 4 <= 12: order 10 (due t2), position 14 > 12
    # t2: +10 -> 14, demand 5 -> 9. position 9 > 0
    result = simulate([5, 5, 5], [4, 12, 0], order_quantity=10, lead_time=0)
    assert result.orders_placed == 1
    assert result.fill_rate == 1
    assert result.average_on_hand == pytest.approx((9 + 4 + 9) / 3)
    assert simulate([], [], 1, 1).periods == 0


def test_replay_argument_errors() -> None:
    with pytest.raises(ValueError, match="whole number"):
        simulate_periodic([1], 5, 1.5, 1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="whole number"):
        simulate_periodic([1], 5, True, 1)
    with pytest.raises(ValueError, match="at least 1"):
        simulate_periodic([1], 5, 0, 1)
    with pytest.raises(ValueError, match="warmup"):
        simulate_periodic([1], 5, 1, 1, warmup=2)
    with pytest.raises(ValueError, match="one level per period: 1 for 2"):
        simulate_periodic([1, 1], [5], 1, 1)
    with pytest.raises(ValueError, match="reorder_point needs one level per period"):
        simulate([1, 1], [5], 1, 1)


# --- policy and levels, by hand ------------------------------------------------------


def test_order_up_to_level_has_the_reorder_point_formula() -> None:
    sq = build_policy(0.95, 10, 4, lead_time=2, review_period=1)
    rs = build_policy(0.95, 10, 4, lead_time=2, review_period=1, kind="RS")
    assert rs.reorder_point == pytest.approx(sq.reorder_point)
    assert (sq.kind, sq.order_up_to) == ("sQ", None)
    assert (rs.kind, rs.order_up_to) == ("RS", rs.reorder_point)
    with pytest.raises(ValueError, match="kind must be"):
        build_policy(0.95, 10, 4, 2, kind="sS")


def test_dynamic_levels_by_hand() -> None:
    # L = 1, R = 1: P = 2. S(t) = mean(F(t+1), F(t+2)) x 2 + 5.
    # t0: (20 + 30) / 2 x 2 + 5 = 55; t1: 75; t2: 95.
    assert dynamic_levels([10, 20, 30, 40, 50], 3, 1, 1, 5) == pytest.approx((55, 75, 95))
    # L = 0.4, R = 0: P rounds to 0 and is taken as 1; S(0) = F(1) x 0.4 = 8.
    assert dynamic_levels([10, 20], 1, 0.4, 0, 0) == pytest.approx((8,))
    with pytest.raises(ValueError, match="must cover 3 periods plus 2 ahead, got 4"):
        dynamic_levels([1, 2, 3, 4], 3, 1, 1, 0)


def test_constant_forecast_gives_the_static_level() -> None:
    static = build_policy(0.95, 12, 3, lead_time=1.5, review_period=1).reorder_point
    levels = dynamic_levels([12.0] * 10, 7, 1.5, 1, static - 12 * 2.5)
    assert levels == pytest.approx((static,) * 7)


def test_calendar_forecasts_by_hand() -> None:
    # Additive Holt-Winters, m = 3, no trend: F(h) = 100 + S((h - 1) mod 3), S = 10, -10, 0.
    # The fit saw periods 0-3; period 4 is 1 step ahead (110), 5 is 2 (90), 6 is 3 (100).
    # Earlier periods take the forecast of the same season position: period 1 is three
    # periods before 4 (110), 2 before 5 (90), 0 and 3 before 6 (100).
    fit = SmoothingFit("hw_additive", 0.5, 0.1, 0.5, 0.1, 100.0, 0.0, (10.0, -10.0, 0.0), 0.0)
    assert fit.calendar_forecasts(4, 7) == (100, 110, 90, 100, 110, 90, 100)
    # Damped Holt, phi = 0.5, L = 10, B = 4: F(1) = 12, F(2) = 10 + 0.75 x 4 = 13.
    # Without a season every earlier period gets the one-step forecast.
    holt = SmoothingFit("holt_damped", 0.5, 0.1, 0.5, None, 10.0, 4.0, (), 0.0)
    assert holt.calendar_forecasts(2, 4) == (12, 12, 12, 13)


# --- configuration and analysis wiring -----------------------------------------------


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        ({"policy": "sS"}, "policy must be 'sQ' or 'RS'"),
        ({"policy": "RS", "review_period": 0}, "whole review period of at least 1, got 0"),
        ({"policy": "RS", "review_period": 1.5}, "whole review period of at least 1, got 1.5"),
        ({"dynamic_levels": True}, "need trend_seasonal"),
    ],
)
def test_config_errors(settings: dict[str, object], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        Config(**settings).validate()  # type: ignore[arg-type]


def test_worked_example_under_rs_by_hand() -> None:
    """W-1: S = 37.91 (the reorder point of the README), R = 1, L = 2.

    With R = 1 every review orders back what was sold, so the replay starts at S
    and on hand at the end of t is S minus the demand of t and of the orders still
    on the way: S - 10, S - 22, S - 30, S - 30, S - 32, S - 30, S - 30, S - 30.
    Mean on hand = S - 214 / 8 = S - 26.75 = 11.16; no stockout; 8 orders.
    """
    report = analyze_file(WORKED, Config(holdout=2, policy="RS"))
    w1 = report.skus[0]
    assert w1.policy.kind == "RS"
    assert w1.policy.order_up_to == pytest.approx(37.91, abs=0.01)
    assert w1.simulation.fill_rate == 1
    assert w1.simulation.average_on_hand == pytest.approx(w1.policy.reorder_point - 26.75)
    assert w1.simulation.orders_placed == 8
    assert w1.simulation == simulate_periodic(
        [10, 12, 8, 10, 14, 6, 10, 14], w1.policy.reorder_point, 1, 2
    )
    assert (w1.levels, w1.next_levels) == ((), ())


def test_zero_forecast_note_only_for_sq() -> None:
    data = parse_rows([["sku", "period", "quantity"]] + [["Z", str(i), "0"] for i in range(1, 9)])
    sq = analyze(data, Config(holdout=2)).skus[0]
    rs = analyze(data, Config(holdout=2, policy="RS")).skus[0]
    assert any("order quantity set to 1 unit" in note for note in sq.notes)
    assert not any("order quantity set to 1 unit" in note for note in rs.notes)
    assert rs.simulation.orders_placed == 0


def test_dynamic_levels_with_a_level_forecast_equal_the_static_level() -> None:
    report = analyze_file(
        WORKED, Config(holdout=2, policy="RS", trend_seasonal=True, dynamic_levels=True)
    )
    w1 = report.skus[0]
    assert w1.method == "moving_average"
    assert "level forecast picked: dynamic levels equal the static level" in w1.notes
    assert w1.levels == pytest.approx((w1.policy.reorder_point,) * 8)
    # One season after the history (12 periods, from --periods-per-year).
    assert w1.next_levels == pytest.approx((w1.policy.reorder_point,) * 12)
    fractional = Config(
        holdout=2, policy="RS", trend_seasonal=True, dynamic_levels=True, periods_per_year=52.18
    )
    assert len(analyze_file(WORKED, fractional).skus[0].next_levels) == 1  # no season: 1
    static = analyze_file(WORKED, Config(holdout=2, policy="RS", trend_seasonal=True)).skus[0]
    assert w1.simulation == static.simulation


def test_seasonal_levels_follow_the_fit() -> None:
    config = Config(policy="RS", trend_seasonal=True, dynamic_levels=True)
    report = analyze(monthly(trend_seasonal_series()), config)
    s = next(r for r in report.skus if r.sku == "S")
    assert s.method == "hw_additive"
    assert (len(s.levels), len(s.next_levels)) == (48, 12)
    # The level at the end of the history is the static S of the same fit.
    assert s.levels[-1] == pytest.approx(s.policy.reorder_point)
    # A +-40 yearly sine: the levels of the next year swing by far more than the noise.
    assert max(s.next_levels) - min(s.next_levels) > 100
    replayed = replay_policy(
        [float(q) for q in trend_seasonal_series()["S"]], s.policy, 1, s.levels
    )
    assert replayed == s.simulation


def test_no_leak_from_the_test_periods_into_dynamic_levels() -> None:
    series = trend_seasonal_series()
    changed = {sku: values[:36] + [0.0] * 12 for sku, values in series.items()}
    config = Config(test_periods=12, trend_seasonal=True, policy="RS", dynamic_levels=True)
    base = analyze(monthly(series), config).out_of_sample
    other = analyze(monthly(changed), config).out_of_sample
    assert base is not None and other is not None
    for a, b in zip(base.skus, other.skus, strict=True):
        assert (a.forecast_method, a.forecast) == (b.forecast_method, b.forecast)
        for ra, rb in zip(a.replays, b.replays, strict=True):
            assert (ra.reorder_point, ra.safety_stock) == (rb.reorder_point, rb.safety_stock)
            assert len(ra.test_levels) == 12
            assert ra.test_levels == rb.test_levels
            assert ra.in_sample == rb.in_sample
    s = next(x for x in base.skus if x.sku == "S").replay("normal")
    assert s.test_levels != (s.test_levels[0],) * 12


# --- rendering and command line ------------------------------------------------------


def test_markdown_and_json_of_an_rs_report() -> None:
    config = Config(policy="RS", review_period=2, test_periods=12)
    report = analyze_file(SYNTHETIC, config)
    text = render_markdown(report)
    assert "- Policy: (R, S) periodic review" in text
    assert "reviewed every 2 period(s)" in text
    assert "| Order-up-to (S) | Review (R) |" in text
    assert "dynamic levels" not in text
    assert "history under the (R, S) policy (in-sample)" in text
    data = json.loads(render_json(report))
    assert (data["settings"]["policy"], data["settings"]["dynamic_levels"]) == ("RS", False)
    policy = data["skus"][0]["policy"]
    assert policy["kind"] == "RS"
    assert policy["order_up_to"] == round(report.skus[0].policy.reorder_point, 4)
    assert (policy["reorder_point"], policy["order_quantity"]) == (None, None)
    assert "levels" not in policy
    replay = data["out_of_sample"]["skus"][0]["policies"]["normal"]
    assert (replay["reorder_point"], replay["order_quantity"]) == (None, None)
    assert replay["order_up_to"] > 0
    assert "test_levels" not in replay


def test_markdown_and_json_with_dynamic_levels() -> None:
    config = Config(test_periods=12, trend_seasonal=True, dynamic_levels=True)
    report = analyze(monthly(trend_seasonal_series()), config)
    text = render_markdown(report)
    assert "- Policy: (s, Q) reorder point" in text
    assert "dynamic levels: s follows the forecast period by period" in text
    assert "lowest and highest level of the next 12 period(s)" in text
    s = next(r for r in report.skus if r.sku == "S")
    low, high = min(s.next_levels), max(s.next_levels)
    assert f"{s.policy.reorder_point:,.1f} ({low:,.1f} to {high:,.1f})" in text
    data = json.loads(render_json(report))
    policy = next(x for x in data["skus"] if x["sku"] == "S")["policy"]
    assert "kind" not in policy and policy["reorder_point"] is not None
    assert (len(policy["levels"]), len(policy["next_levels"])) == (48, 12)
    replay = data["out_of_sample"]["skus"][1]["policies"]["bootstrap"]
    assert len(replay["test_levels"]) == 12 and replay["order_quantity"] > 0


def test_default_report_is_unchanged_by_the_new_options() -> None:
    report = analyze_file(SYNTHETIC)
    text = render_markdown(report)
    assert "- Policy:" not in text and "| Reorder point (s) | Order qty (Q) |" in text
    data = json.loads(render_json(report))
    assert (data["settings"]["policy"], data["settings"]["dynamic_levels"]) == ("sQ", False)
    assert set(data["skus"][0]["policy"]) == {
        "service_level",
        "z",
        "demand_per_period",
        "sigma_demand",
        "lead_time",
        "sigma_lead_time",
        "review_period",
        "safety_stock",
        "safety_stock_method",
        "reorder_point",
        "eoq",
        "order_quantity",
        "order_quantity_source",
    }


def test_cli_options(capsys: pytest.CaptureFixture[str]) -> None:
    from inventory_policy_lab.cli import main

    args = [str(SYNTHETIC), "--policy", "RS", "--review-period", "3", "--format", "json"]
    assert main(args) == 0
    data = json.loads(capsys.readouterr().out)
    assert (data["settings"]["policy"], data["settings"]["review_period"]) == ("RS", 3.0)
    assert main([*args, "--trend-seasonal", "--dynamic-levels"]) == 0
    assert json.loads(capsys.readouterr().out)["settings"]["dynamic_levels"] is True
    assert main([str(SYNTHETIC), "--dynamic-levels"]) == 2
    assert "need trend_seasonal (--trend-seasonal)" in capsys.readouterr().err
    assert main([str(SYNTHETIC), "--policy", "RS", "--review-period", "0.5"]) == 2
    assert "whole review period" in capsys.readouterr().err


# --- results quoted in the README and ADR 0007 ---------------------------------------


def _totals(config: Config, series: bool = False) -> dict[str, tuple[float, int, float]]:
    """Out-of-sample totals of the 24-month example, or of the 48-month series."""
    report = (
        analyze(monthly(trend_seasonal_series()), config)
        if series
        else analyze_file(SYNTHETIC, config)
    )
    oos = report.out_of_sample
    assert oos is not None
    return {
        method: (round(t.fill_rate or 0, 3), t.stockout_periods, round(t.average_on_hand, 1))
        for method in ("normal", "bootstrap")
        for t in [oos.totals(method, "out_of_sample")]
    }


POLICIES = {
    "sQ, level forecasts (0.2.0)": {},
    "sQ static": {"trend_seasonal": True},
    "RS static": {"trend_seasonal": True, "policy": "RS"},
    "RS dynamic": {"trend_seasonal": True, "policy": "RS", "dynamic_levels": True},
    "sQ dynamic": {"trend_seasonal": True, "dynamic_levels": True},
    "RS static, R=3": {"trend_seasonal": True, "policy": "RS", "review_period": 3},
    "RS dynamic, R=3": {
        "trend_seasonal": True,
        "policy": "RS",
        "review_period": 3,
        "dynamic_levels": True,
    },
    "RS dynamic, sigma rmse": {
        "trend_seasonal": True,
        "policy": "RS",
        "dynamic_levels": True,
        "sigma": "rmse",
    },
}


def test_48_month_series_results_quoted_in_the_readme() -> None:
    """36 training and 12 test months; (fill rate, stockout periods, avg on hand summed)."""
    results = {
        name: _totals(Config(test_periods=12, **settings), series=True)  # type: ignore[arg-type]
        for name, settings in POLICIES.items()
    }
    assert results == {
        "sQ, level forecasts (0.2.0)": {
            "normal": (0.975, 3, 189.8),
            "bootstrap": (0.966, 5, 172.4),
        },
        "sQ static": {"normal": (0.996, 1, 289.0), "bootstrap": (0.976, 4, 196.4)},
        "RS static": {"normal": (0.974, 4, 140.0), "bootstrap": (0.855, 19, 79.4)},
        "RS dynamic": {"normal": (1.0, 0, 105.5), "bootstrap": (0.893, 22, 41.0)},
        "sQ dynamic": {"normal": (1.0, 0, 269.9), "bootstrap": (0.988, 2, 174.8)},
        "RS static, R=3": {"normal": (0.996, 2, 589.1), "bootstrap": (0.924, 7, 389.3)},
        "RS dynamic, R=3": {"normal": (0.999, 1, 439.3), "bootstrap": (0.904, 10, 247.0)},
        "RS dynamic, sigma rmse": {"normal": (0.892, 21, 14.3), "bootstrap": (0.893, 22, 41.0)},
    }


def test_48_month_series_per_sku_quoted_in_the_readme() -> None:
    config = Config(test_periods=12, trend_seasonal=True, policy="RS", dynamic_levels=True)
    oos = analyze(monthly(trend_seasonal_series()), config).out_of_sample
    assert oos is not None
    quoted = {
        (s.sku, r.method): (
            round(r.out_of_sample.fill_rate or 0, 3),
            r.out_of_sample.stockout_periods,
            round(r.out_of_sample.average_on_hand, 1),
        )
        for s in oos.skus
        for r in s.replays
    }
    assert quoted == {
        ("S", "normal"): (1.0, 0, 60.0),
        ("S", "bootstrap"): (1.0, 0, 39.2),
        ("T", "normal"): (1.0, 0, 24.9),
        ("T", "bootstrap"): (0.784, 12, 0.0),
        ("TS", "normal"): (1.0, 0, 20.6),
        ("TS", "bootstrap"): (0.917, 10, 1.7),
    }
    t = next(s for s in oos.skus if s.sku == "T").replay("bootstrap")
    assert t.safety_stock == 0  # bootstrap quantile below the naive forecast of a trend


def test_synthetic_example_results_quoted_in_the_readme() -> None:
    results = {
        name: _totals(Config(test_periods=12, **settings))  # type: ignore[arg-type]
        for name, settings in POLICIES.items()
    }
    assert results == {
        "sQ, level forecasts (0.2.0)": {
            "normal": (0.944, 11, 885.2),
            "bootstrap": (0.946, 12, 712.4),
        },
        "sQ static": {"normal": (0.944, 11, 885.2), "bootstrap": (0.946, 12, 712.4)},
        "RS static": {"normal": (0.909, 20, 598.6), "bootstrap": (0.907, 17, 427.9)},
        "RS dynamic": {"normal": (0.909, 20, 598.6), "bootstrap": (0.907, 17, 427.9)},
        "sQ dynamic": {"normal": (0.944, 11, 885.2), "bootstrap": (0.946, 12, 712.4)},
        "RS static, R=3": {"normal": (0.934, 11, 1306.6), "bootstrap": (0.942, 11, 1032.1)},
        "RS dynamic, R=3": {"normal": (0.934, 11, 1306.6), "bootstrap": (0.942, 11, 1032.1)},
        "RS dynamic, sigma rmse": {"normal": (0.874, 23, 561.9), "bootstrap": (0.907, 17, 427.9)},
    }
