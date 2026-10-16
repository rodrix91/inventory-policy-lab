"""Cost of the out-of-sample replay (ADR 0012): by hand, wiring, validation, defaults."""

from __future__ import annotations

import json
import math
from dataclasses import replace

import pytest
from conftest import EXAMPLES, run_module
from test_rolling import HAND, HAND_CONFIG
from test_smoothing import integer

from inventory_policy_lab import (
    Config,
    ConfigError,
    CostBreakdown,
    CostRates,
    analyze,
    analyze_file,
    render_json,
    render_markdown,
    replay_cost,
    simulate,
    total_cost,
)

SYNTHETIC = EXAMPLES / "demand_synthetic.csv"


def _priced(config: Config) -> Config:
    """``config`` with 5 per order, 1 per unit-period held and 4 per unit short."""
    return replace(config, order_cost=5.0, holding_cost=1.0, stockout_cost=4.0)


# --- one replay, by hand -------------------------------------------------------------


def test_replay_cost_by_hand() -> None:
    """(s = 4, Q = 8), L = 1 (orders arrive two periods after the end of their period).

    Start with s + Q = 12 on hand.
      t0: serve 4 -> 8 on hand; position 8 > 4.
      t1: serve 4 -> 4; position 4 <= 4: order 8 (due t3), position 12.
      t2: serve 6 of 4 on hand -> -2 (2 units short, backordered); position 6 > 4.
      t3: receive 8 -> 6, serve 4 -> 2; position 2: order 8 (due t5).
    Orders 2, stock on hand at the ends 8 + 4 + 0 + 2 = 14 unit-periods, 2 units short.
    At 10 per order, 0.5 per unit-period and 3 per unit short: 20 + 7 + 6 = 33.
    Scoring only t2 and t3 (warm-up 2): 1 order, 0 + 2 = 2 unit-periods, 2 short:
    10 + 1 + 6 = 17.
    """
    rates = CostRates(order=10, holding=0.5, stockout=3)
    cost = replay_cost(simulate([4, 4, 6, 4], 4, 8, lead_time=1), rates)
    assert (cost.orders, cost.unit_periods, cost.units_short) == (2, 14, 2)
    assert (cost.ordering, cost.holding, cost.stockout, cost.total) == (20, 7, 6, 33)
    scored = replay_cost(simulate([4, 4, 6, 4], 4, 8, lead_time=1, warmup=2), rates)
    assert (scored.orders, scored.unit_periods, scored.units_short) == (1, 2, 2)
    assert scored.total == 17


def test_total_cost_adds_part_by_part() -> None:
    a = CostBreakdown(orders=2, unit_periods=14, units_short=2, ordering=20, holding=7, stockout=6)
    b = CostBreakdown(orders=1, unit_periods=2, units_short=0, ordering=10, holding=1, stockout=0)
    total = total_cost([a, b])
    assert total == CostBreakdown(3, 16, 2, 30, 8, 6)
    assert total.total == 44
    assert total_cost([]).total == 0


@pytest.mark.parametrize("value", [-1.0, math.nan, math.inf])
def test_cost_rates_must_be_finite_and_not_negative(value: float) -> None:
    with pytest.raises(ValueError, match="holding cost must be a finite number"):
        CostRates(holding=value)


# --- the report, by hand -------------------------------------------------------------


def test_out_of_sample_cost_by_hand() -> None:
    """The case of ``test_rolling.test_rolling_origin_by_hand`` (L = 0), priced.

    Fixed (s = 10, Q = 10): t4 ends at 0 and orders twice; t5 is 10 short and
    orders 3 x 10; t6 is 10 short and orders 3 x 10: 8 orders, no stock left at
    any end, 20 units short. At 5 per order, 1 per unit-period and 4 per unit
    short: 40 + 0 + 80 = 120.
    Rolling: t4 as fixed (2 orders); t5 is 10 short, s = 27.36 and Q = 20 order
    twice (to 10 and 30); t6 receives 40 -> 30, serves 30 -> 0, s = 43.76 and
    Q = 30 order twice: 6 orders, 10 short: 30 + 0 + 40 = 70. The bootstrap has
    the same levels where it matters (10, 20, 30) and the same orders.
    """
    oos = analyze(integer(HAND), _priced(HAND_CONFIG)).out_of_sample
    assert oos is not None and oos.costs == CostRates(5, 1, 4)
    for method in ("normal", "bootstrap"):
        fixed, rolling = oos.cost(method, "fixed"), oos.cost(method, "rolling")
        assert (fixed.orders, fixed.unit_periods, fixed.units_short) == (8, 0, 20)
        assert (fixed.ordering, fixed.holding, fixed.stockout, fixed.total) == (40, 0, 80, 120)
        assert (rolling.orders, rolling.units_short, rolling.total) == (6, 10, 70)
    (sku,) = oos.skus
    assert oos.sku_cost(sku, "normal") == oos.cost("normal")


def test_unset_costs_count_as_zero() -> None:
    config = replace(HAND_CONFIG, stockout_cost=4.0)
    assert config.cost_rates == CostRates(0, 0, 4)
    oos = analyze(integer(HAND), config).out_of_sample
    assert oos is not None
    assert oos.cost("normal").total == 80
    assert Config().cost_rates is None


def test_report_totals_are_the_sum_of_the_skus() -> None:
    config = _priced(Config(test_periods=12, rolling_origin=True))
    oos = analyze_file(SYNTHETIC, config).out_of_sample
    assert oos is not None
    for method in ("normal", "bootstrap"):
        for origin in ("fixed", "rolling"):
            parts = [oos.sku_cost(s, method, origin) for s in oos.skus]
            assert oos.cost(method, origin) == total_cost(parts)
            replays = [
                (s.replay(method) if origin == "fixed" else s.rolling_replay(method)).out_of_sample
                for s in oos.skus
            ]
            assert sum(r.orders_placed for r in replays) == oos.cost(method, origin).orders


def test_cost_needs_rates_and_a_known_origin() -> None:
    oos = analyze(integer(HAND), HAND_CONFIG).out_of_sample
    assert oos is not None and oos.costs is None
    with pytest.raises(ValueError, match="no cost rates"):
        oos.cost("normal")
    priced = analyze(integer(HAND), _priced(HAND_CONFIG)).out_of_sample
    assert priced is not None
    with pytest.raises(ValueError, match="origin must be 'fixed' or 'rolling'"):
        priced.cost("normal", "moving")


# --- settings ------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["order_cost", "holding_cost", "stockout_cost"])
@pytest.mark.parametrize("value", [-0.5, math.nan])
def test_config_rejects_bad_costs(name: str, value: float) -> None:
    label = name.replace("_", " ")
    with pytest.raises(ConfigError, match=f"{label} must be a finite number"):
        config = Config(test_periods=3)
        if name == "order_cost":
            config = replace(config, order_cost=value)
        elif name == "holding_cost":
            config = replace(config, holding_cost=value)
        else:
            config = replace(config, stockout_cost=value)
        config.validate()


def test_costs_need_test_periods() -> None:
    with pytest.raises(ConfigError, match="need test periods"):
        Config(holding_cost=1.0).validate()


# --- output --------------------------------------------------------------------------


def test_markdown_and_json_with_costs() -> None:
    config = _priced(HAND_CONFIG)
    report = analyze(integer(HAND), config)
    text = render_markdown(report)
    assert "### Cost of the test periods (5 to 7)" in text
    assert "Rates: 5 per order placed, 1 per unit on hand" in text
    assert "| normal | fixed | 8 | 0.0 | 20.0 | 40.0 | 0.0 | 80.0 | **120.0** |" in text
    assert "| normal | rolling | 6 | 0.0 | 10.0 | 30.0 | 0.0 | 40.0 | **70.0** |" in text
    assert "| A | bootstrap | rolling | 30.0 | 0.0 | 40.0 | 70.0 |" in text
    data = json.loads(render_json(report))
    settings = data["settings"]
    assert (settings["order_cost"], settings["holding_cost"], settings["stockout_cost"]) == (
        5.0,
        1.0,
        4.0,
    )
    costs = data["out_of_sample"]["costs"]
    assert costs["rates"] == {"order": 5.0, "holding": 1.0, "stockout": 4.0}
    assert costs["summary"]["normal"]["fixed"] == {
        "orders": 8,
        "unit_periods": 0.0,
        "units_short": 20.0,
        "ordering": 40.0,
        "holding": 0.0,
        "stockout": 80.0,
        "total": 120.0,
    }
    assert costs["skus"][0]["policies"]["bootstrap"]["rolling"]["total"] == 70.0


def test_fixed_origin_only_without_rolling() -> None:
    config = _priced(replace(HAND_CONFIG, rolling_origin=False))
    report = analyze(integer(HAND), config)
    data = json.loads(render_json(report))
    assert list(data["out_of_sample"]["costs"]["summary"]["normal"]) == ["fixed"]
    assert "| normal | rolling |" not in render_markdown(report)


def test_reports_without_costs_have_no_cost_keys() -> None:
    report = analyze(integer(HAND), HAND_CONFIG)
    data = json.loads(render_json(report))
    assert "costs" not in data["out_of_sample"]
    assert not {"order_cost", "holding_cost", "stockout_cost"} & set(data["settings"])
    assert "Cost of the test periods" not in render_markdown(report)


def test_cli_options() -> None:
    args = [str(SYNTHETIC), "--test-periods", "12", "--format", "json"]
    proc = run_module(*args, "--order-cost", "50", "--holding-cost", "0.5")
    assert proc.returncode == 0, proc.stderr
    rates = json.loads(proc.stdout)["out_of_sample"]["costs"]["rates"]
    assert rates == {"order": 50.0, "holding": 0.5, "stockout": 0.0}
    bad = run_module(str(SYNTHETIC), "--stockout-cost", "10")
    assert bad.returncode == 2
    assert "need test periods (--test-periods N)" in bad.stderr
    negative = run_module(*args, "--order-cost", "-1")
    assert negative.returncode == 2
    assert "order cost must be a finite number of at least 0" in negative.stderr
