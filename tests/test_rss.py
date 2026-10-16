"""Periodic-review (R, s, S) policy (ADR 0013): replay by hand, wiring, no leak, output."""

from __future__ import annotations

import json
import random
from dataclasses import replace
from functools import cache

import pytest
from conftest import EXAMPLES, run_module
from test_rolling import HAND, HAND_CONFIG
from test_smoothing import integer, monthly, trend_seasonal_series

from inventory_policy_lab import (
    Config,
    ConfigError,
    OutOfSampleReport,
    analyze,
    analyze_file,
    build_policy,
    read_demand,
    render_json,
    render_markdown,
    replay_policy,
    simulate_periodic,
    simulate_rss,
)

SYNTHETIC = EXAMPLES / "demand_synthetic.csv"


# --- the replay, by hand -------------------------------------------------------------


def test_simulate_rss_by_hand() -> None:
    """R = 2, s = 5, Q = 5 (S = 10), L = 1: an order arrives two periods after its review.

    Start with s + Q = 10 on hand. Reviews at the end of periods 1, 3 and 5.
      t0: serve 2 -> 8.
      t1: serve 2 -> 6; review: position 6 > s = 5, no order ((R, S) would order 4).
      t2: serve 5 -> 1.
      t3: serve 1 of 5 -> -4 (4 short); review: position -4 <= 5, order S + 4 = 14 (due t5).
      t4: serve 0 of 2 -> -6 (2 short).
      t5: receive 14 -> 8, serve 2 -> 6; review: 6 > 5, no order.
    Served 2 + 2 + 5 + 1 + 0 + 2 = 12 of 18; stockouts at t3 and t4; on hand
    8 + 6 + 1 + 0 + 0 + 6 = 21 (mean 3.5); one order; largest backorder 6.
    """
    result = simulate_rss([2, 2, 5, 5, 2, 2], 5, 5, review_period=2, lead_time=1)
    assert result.served_from_stock == 12
    assert result.fill_rate == pytest.approx(12 / 18)
    assert (result.stockout_periods, result.orders_placed, result.max_backorder) == (2, 1, 6)
    assert result.average_on_hand == 3.5
    # Scoring only t3 to t5: 3 of 9 served, 2 stockouts, 0 + 0 + 6 on hand, the order at t3.
    scored = simulate_rss([2, 2, 5, 5, 2, 2], 5, 5, review_period=2, lead_time=1, warmup=3)
    assert (scored.served_from_stock, scored.stockout_periods, scored.orders_placed) == (3, 2, 1)
    assert scored.average_on_hand == 2


def test_no_order_above_s_by_hand() -> None:
    """R = 1, s = 4, Q = 4 (S = 8), L = 0. Start with 8.

    t0: 7 > 4 and t1: 6 > 4, no order; t2: 3 <= 4, order 8 - 3 = 5 (due t3);
    t3: receive 5 -> 8, serve 6 -> 2 <= 4, order 6. Two orders, on hand 7 + 6 + 3 + 2.
    (R, S) with S = 8 would order at every review: four orders.
    """
    result = simulate_rss([1, 1, 3, 6], 4, 4, review_period=1, lead_time=0)
    assert (result.orders_placed, result.fill_rate, result.average_on_hand) == (2, 1.0, 4.5)
    assert simulate_periodic([1, 1, 3, 6], 8, 1, 0).orders_placed == 4


def test_levels_and_quantities_per_period_by_hand() -> None:
    """s = 5, 2, 5 and Q = 10, 3, 1 by period, R = 1, L = 0: start with s(0) + Q(0) = 15.

    t0: 10 > 5; t1: 5 > 2; t2: 0 <= 5, order up to s(2) + Q(2) = 6. One order.
    """
    result = simulate_rss([5, 5, 5], [5, 2, 5], [10, 3, 1], review_period=1, lead_time=0)
    assert (result.orders_placed, result.fill_rate, result.average_on_hand) == (1, 1.0, 5)


def test_a_quantity_of_one_unit_is_the_order_up_to_policy() -> None:
    # With whole demands and levels, "position <= s" is "position < s + 1", so
    # (R, s, S) with Q = 1 is (R, S) with S = s + 1, which also starts with s + 1.
    rng = random.Random(13)
    for _ in range(200):
        demand = [float(rng.choice([0, 0, 1, 2, 3, 5, 8])) for _ in range(rng.randint(1, 15))]
        s, review, lead = rng.randint(0, 12), rng.randint(1, 3), rng.randint(0, 2)
        warmup = rng.randint(0, len(demand))
        assert simulate_rss(demand, s, 1, review, lead, warmup) == simulate_periodic(
            demand, s + 1, review, lead, warmup
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"order_quantity": 0}, "order_quantity must be positive"),
        ({"order_quantity": [1, 0]}, "order_quantity must be positive"),
        ({"order_quantity": [1]}, "one level per period: 1 for 2"),
        ({"reorder_point": [1, 2, 3]}, "one level per period: 3 for 2"),
        ({"review_period": 0}, "review_period must be at least 1"),
        ({"review_period": True}, "review_period must be a whole number"),
        ({"warmup": 3}, "warmup must be between 0"),
    ],
)
def test_simulate_rss_errors(kwargs: dict[str, object], message: str) -> None:
    arguments: dict[str, object] = {
        "demand": [1, 1],
        "reorder_point": 1,
        "order_quantity": 2,
        "review_period": 1,
        "lead_time": 0,
        **kwargs,
    }
    with pytest.raises(ValueError, match=message):
        simulate_rss(**arguments)  # type: ignore[arg-type]


def test_replay_policy_dispatches_to_rss() -> None:
    policy = build_policy(0.95, 2.0, 0.0, 0.0, review_period=1, kind="RsS")
    assert (policy.kind, policy.reorder_point, policy.order_up_to) == ("RsS", 2.0, None)
    demand = [1.0, 1.0, 3.0, 6.0]
    assert replay_policy(demand, policy, 4) == simulate_rss(demand, 2, 4, 1, 0)
    assert replay_policy(demand, policy, 4, [4, 4, 4, 4]) == simulate_rss(demand, 4, 4, 1, 0)


# --- the analysis, by hand -----------------------------------------------------------


def test_out_of_sample_by_hand() -> None:
    """The case of ``test_rolling.test_rolling_origin_by_hand`` (L = 0, R = 1) under (R, s, S).

    Train fit: s = 10, Q = 10, S = 20. Training replay starts with 20; every period
    ends with 10 on hand and orders back up to 20: 4 orders, 100%, mean stock 10.
    Fixed test: t4 receives 10 -> 20, serves 20 -> 0, orders 20; t5 receives 20,
    serves 30 -> -10, orders 30; t6 receives 30 -> 20, serves 30 -> -10, orders 30.
    3 orders (against 8 for (s, Q), which orders in multiples of Q), 20 short, 75%.
    Rolling, normal: t5 has s = 27.356, Q = 20, so S = 47.356 and the order is 57.356;
    t6 receives it -> 47.356, serves 30 -> 17.356 on hand, orders up to 73.762.
    10 short (87.5%), 3 orders, stock 0 + 0 + 17.356. At 5 / 1 / 4:
    fixed 15 + 0 + 80 = 95; rolling 15 + 17.356 + 40 = 72.356.
    """
    config = replace(HAND_CONFIG, policy="RsS", order_cost=5.0, holding_cost=1.0, stockout_cost=4.0)
    oos = analyze(integer(HAND), config).out_of_sample
    assert oos is not None and oos.policy == "RsS"
    (sku,) = oos.skus
    fixed = sku.replay("normal")
    assert (fixed.reorder_point, fixed.order_quantity) == (10, 10)
    assert (fixed.in_sample.orders_placed, fixed.in_sample.average_on_hand) == (4, 10)
    assert fixed.out_of_sample.fill_rate == 0.75
    assert oos.cost("normal").orders == 3
    assert oos.cost("normal").total == 95
    rolling = sku.rolling_replay("normal")
    assert rolling.order_quantities == (10, 20, 30)
    assert rolling.out_of_sample.fill_rate == 0.875
    assert rolling.out_of_sample.average_on_hand * 3 == pytest.approx(17.356009, abs=1e-6)
    assert oos.cost("normal", "rolling").total == pytest.approx(72.356009, abs=1e-6)


def test_needs_a_whole_review_period() -> None:
    with pytest.raises(ConfigError, match=r"an \(R, s, S\) policy needs a whole review period"):
        Config(policy="RsS", review_period=1.5).validate()
    with pytest.raises(ConfigError, match=r"an \(R, s, S\) policy needs a whole review period"):
        Config(policy="RsS", review_period=0).validate()


def test_zero_forecast_gets_a_one_unit_quantity() -> None:
    report = analyze(integer({"A": [0.0] * 8, "B": [5.0] * 8}), Config(policy="RsS"))
    zero = report.skus[0]
    assert (zero.order_quantity, zero.order_quantity_source) == (1.0, "minimum")
    assert "forecast is zero: order quantity set to 1 unit for the replay" in zero.notes


@cache
def _series_report(cut: int | None = None, every: int = 1) -> OutOfSampleReport:
    """The 48-month series (36 train, 12 test) under (R, s, S) R = 1, dynamic levels,
    residual bootstrap, rolling origin; with ``cut``, periods from it on are zero."""
    series = trend_seasonal_series()
    if cut is not None:
        series = {sku: values[:cut] + [0.0] * (48 - cut) for sku, values in series.items()}
    config = Config(
        test_periods=12,
        trend_seasonal=True,
        policy="RsS",
        dynamic_levels=True,
        bootstrap_source="residuals",
        rolling_origin=True,
        refit_every=every,
    )
    oos = analyze(monthly(series), config).out_of_sample
    assert oos is not None
    return oos


def test_no_leak_from_later_test_periods() -> None:
    # Periods 40 to 47 become zero: the decisions of origins 36 to 40 cannot move.
    base, other = _series_report(), _series_report(40)
    kept = 40 - 36 + 1
    moved = False
    for a, b in zip(base.skus, other.skus, strict=True):
        for ra, rb in zip(a.replays, b.replays, strict=True):
            assert (ra.reorder_point, ra.order_quantity, ra.test_levels) == (
                rb.reorder_point,
                rb.order_quantity,
                rb.test_levels,
            )
        for qa, qb in zip(a.rolling, b.rolling, strict=True):
            assert qa.levels[:kept] == qb.levels[:kept]
            assert qa.safety_stocks[:kept] == qb.safety_stocks[:kept]
            assert qa.order_quantities[:kept] == qb.order_quantities[:kept]
            moved = moved or qa.levels[kept:] != qb.levels[kept:]
    assert moved


def test_refitting_once_for_the_whole_test_is_the_fixed_origin() -> None:
    oos = _series_report(every=12)
    for sku in oos.skus:
        for method in ("normal", "bootstrap"):
            assert sku.rolling_replay(method).out_of_sample == sku.replay(method).out_of_sample


# --- output --------------------------------------------------------------------------


def test_markdown_and_json() -> None:
    config = Config(policy="RsS", review_period=3, test_periods=12, rolling_origin=True)
    report = analyze_file(SYNTHETIC, config)
    text = render_markdown(report)
    assert "- Policy: (R, s, S) periodic review, reorder level s = D x (L + R) + SS" in text
    assert "order-up-to level S = s + Q" in text
    assert "| Reorder level (s) | Order qty (Q = S - s) | Review (R) |" in text
    assert "under the (R, s, S) policy (in-sample)" in text
    data = json.loads(render_json(report))
    assert data["settings"]["policy"] == "RsS"
    first = data["skus"][0]["policy"]
    assert first["kind"] == "RsS"
    assert first["order_up_to"] == pytest.approx(
        first["reorder_point"] + first["order_quantity"], abs=1e-3
    )
    replay = data["out_of_sample"]["skus"][0]["policies"]["normal"]
    assert replay["order_up_to"] == pytest.approx(
        replay["reorder_point"] + replay["order_quantity"], abs=1e-3
    )
    rolling = data["out_of_sample"]["rolling_origin"]["skus"][0]["policies"]["normal"]
    assert len(rolling["reorder_points"]) == len(rolling["order_quantities"]) == 12


def test_cli_option() -> None:
    proc = run_module(str(SYNTHETIC), "--policy", "RsS", "--review-period", "3")
    assert proc.returncode == 0, proc.stderr
    assert "(R, s, S) periodic review" in proc.stdout
    bad = run_module(str(SYNTHETIC), "--policy", "RsS", "--review-period", "0.5")
    assert bad.returncode == 2
    assert "whole review period of at least 1" in bad.stderr


# --- the cost table of the README ----------------------------------------------------

POLICIES = (("sQ", 1), ("RS", 1), ("RS", 3), ("RsS", 1), ("RsS", 3))
# Fill rate (%) and total cost per policy, in the README order: normal fixed, normal
# rolling, residual bootstrap fixed, residual bootstrap rolling. Rates 50 / 1 / 10.
TABLE_48 = {
    ("sQ", 1): ((100.0, 5139), (100.0, 5112), (99.8, 3951), (99.9, 3869)),
    ("RS", 1): ((100.0, 3066), (100.0, 3592), (95.4, 3732), (99.4, 2482)),
    ("RS", 3): ((99.9, 5924), (100.0, 6859), (97.2, 5499), (99.4, 5520)),
    ("RsS", 1): ((100.0, 5801), (100.0, 5905), (99.9, 4540), (100.0, 4404)),
    ("RsS", 3): ((100.0, 9836), (100.0, 10764), (100.0, 8262), (100.0, 9159)),
}
TABLE_24 = {
    ("sQ", 1): ((94.4, 21371), (99.8, 17735), (92.2, 23849), (98.5, 19178)),
    ("RS", 1): ((90.9, 17313), (97.3, 13405), (88.5, 19956), (96.0, 14813)),
    ("RS", 3): ((93.4, 21594), (97.0, 19353), (92.9, 25599), (96.9, 23004)),
    ("RsS", 1): ((99.3, 15576), (100.0, 15818), (97.9, 17490), (99.5, 16632)),
    ("RsS", 3): ((97.9, 25065), (99.3, 24634), (96.7, 29523), (98.4, 29018)),
}


def _cost_cells(oos: OutOfSampleReport) -> tuple[tuple[float, int], ...]:
    cells = []
    for method in ("normal", "bootstrap"):
        for origin in ("fixed", "rolling"):
            totals = (
                oos.totals(method, "out_of_sample")
                if origin == "fixed"
                else oos.rolling_totals(method)
            )
            assert totals.fill_rate is not None
            cost = oos.cost(method, origin)
            cells.append((round(totals.fill_rate * 100, 1), round(cost.total)))
    return tuple(cells)


@pytest.mark.parametrize(("name", "table"), [("48", TABLE_48), ("24", TABLE_24)])
def test_cost_table_quoted_in_the_readme(
    name: str, table: dict[tuple[str, int], tuple[tuple[float, int], ...]]
) -> None:
    data = monthly(trend_seasonal_series()) if name == "48" else read_demand(SYNTHETIC)
    for policy, review in POLICIES:
        config = Config(
            test_periods=12,
            trend_seasonal=True,
            bootstrap_source="residuals",
            rolling_origin=True,
            policy=policy,
            review_period=review,
            dynamic_levels=True,
            order_cost=50.0,
            holding_cost=1.0,
            stockout_cost=10.0,
        )
        oos = analyze(data, config).out_of_sample
        assert oos is not None
        assert _cost_cells(oos) == table[(policy, review)], (name, policy, review)
