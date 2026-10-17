"""Cost-optimised safety stock and order quantity (ADR 0015)."""

from __future__ import annotations

import json
import random
from dataclasses import replace

import pytest
from conftest import EXAMPLES, run_module
from test_smoothing import monthly, trend_seasonal_series

from inventory_policy_lab import (
    Config,
    ConfigError,
    CostRates,
    analyze,
    analyze_file,
    read_demand,
    render_json,
    render_markdown,
    replay_cost,
    replay_policy,
    simulate,
    simulate_rss,
)
from inventory_policy_lab.optimize import (
    COVER_PERIODS,
    FORECAST_SHARES,
    REFINE_STEPS,
    SAFETY_Z,
    demand_paths,
    expected_costs,
    quantity_grid,
    safety_grid,
    search_levels,
)
from inventory_policy_lab.validation import _optimized_replay

SYNTHETIC = EXAMPLES / "demand_synthetic.csv"
RATES = CostRates(order=2, holding=1, stockout=3)


def _priced(**settings: object) -> Config:
    base: dict[str, object] = {
        "test_periods": 12,
        "trend_seasonal": True,
        "order_cost": 50.0,
        "holding_cost": 1.0,
        "stockout_cost": 10.0,
        "optimize_cost": True,
        "optimize_samples": 20,
    }
    base.update(settings)
    return Config(**base)  # type: ignore[arg-type]


# --- expected cost of one candidate, by hand -----------------------------------------


def test_expected_costs_by_hand() -> None:
    """(s, Q), L = 0: orders arrive at the start of the next period.

    Training: one period of 10 at level 5, Q = 10; the run starts with 15 on
    hand, serves 10 (5 left) and orders 10 for period 1. Both paths start there.
    Path [10, 10]:
      (SS 0, Q 10), levels 5: t1 receives 10 -> 15, serves 10 -> 5, orders; t2 the
      same. 2 orders, 5 + 5 = 10 unit-periods, nothing short: 4 + 10 = 14.
      (SS -5, Q 10), levels 0: t1 15 -> 5, no order; t2 serves 5 of 10 (5 short),
      orders once. 1 order, 5 unit-periods, 5 short: 2 + 5 + 15 = 22.
    Path [0, 0]: 15 on hand at both ends and no order for either: 30.
    Means: 22 and 26.
    """
    costs = expected_costs(
        [10.0],
        [5.0],
        10.0,
        "sQ",
        1,
        0.0,
        [5.0, 5.0],
        [[10.0, 10.0], [0.0, 0.0]],
        RATES,
        [(0.0, 10.0), (-5.0, 10.0)],
    )
    assert costs == [22.0, 26.0]
    found = search_levels(
        [10.0],
        [5.0],
        10.0,
        "sQ",
        1,
        0.0,
        [5.0, 5.0],
        [[10.0, 10.0], [0.0, 0.0]],
        RATES,
        [-5.0, 0.0],
        [10.0],
    )
    assert (found.safety_stock, found.order_quantity, found.expected_cost) == (0.0, 10.0, 22.0)
    assert (found.heuristic_safety_stock, found.heuristic_cost) == (-5.0, 26.0)
    assert (found.candidates, found.samples) == (2, 2)


def test_ties_keep_the_heuristic_pair() -> None:
    # Without demand nothing is ever ordered or short: every pair costs the same.
    found = search_levels(
        [0.0], [5.0], 10.0, "sQ", 1, 0.0, [5.0], [[0.0]], RATES, [3.0, 0.0, 9.0], [10.0, 20.0]
    )
    assert (found.safety_stock, found.order_quantity) == (3.0, 10.0)
    assert found.expected_cost == found.heuristic_cost


def test_refinement_moves_the_safety_stock_in_steps() -> None:
    """The grid offers -5 and 0; a step of 1 lets the refinement find a level in between.

    Path [10, 10], L = 0, Q = 10, holding 1 and stockout 3: from SS -5 (22) to SS 0 (14)
    the cost falls as the shortage falls; a refinement around 0 cannot do better than 0
    upwards (more stock), and -1 to -4 leave units short, so the pick stays 0 with
    8 more candidates scored.
    """
    found = search_levels(
        [10.0],
        [5.0],
        10.0,
        "sQ",
        1,
        0.0,
        [5.0, 5.0],
        [[10.0, 10.0]],
        RATES,
        [-5.0, 0.0],
        [10.0],
        refine_step=1.0,
    )
    assert found.candidates == 2 + len(REFINE_STEPS)
    assert found.safety_stock == 0.0 and found.expected_cost == 14.0
    # A refinement that does find a cheaper level: start from a grid of -5 only.
    better = search_levels(
        [10.0],
        [5.0],
        10.0,
        "sQ",
        1,
        0.0,
        [5.0, 5.0],
        [[10.0, 10.0]],
        RATES,
        [-5.0],
        [10.0],
        refine_step=1.25,
    )
    assert better.safety_stock == pytest.approx(0.0) and better.expected_cost < 22.0


@pytest.mark.parametrize(("kind", "review"), [("sQ", 1), ("RsS", 1), ("RsS", 2)])
def test_expected_costs_equal_the_simulator(kind: str, review: int) -> None:
    """Pricing a path after the training warm-up is pricing the simulator's replay."""
    rng = random.Random(f"{kind}{review}")
    for _ in range(30):
        train = [rng.choice([0.0, 4.0, 9.0, 15.0]) for _ in range(rng.randint(1, 6))]
        levels = [rng.uniform(0, 20) for _ in train]
        quantity = rng.uniform(1, 15)
        horizon = rng.randint(1, 5)
        base = [rng.uniform(-5, 20) for _ in range(horizon)]
        paths = [[rng.choice([0.0, 3.0, 8.0, 20.0]) for _ in base] for _ in range(4)]
        lead = rng.choice([0.0, 1.0, 2.0])
        pairs = [(rng.uniform(-5, 5), rng.uniform(1, 15)) for _ in range(3)]
        got = expected_costs(train, levels, quantity, kind, review, lead, base, paths, RATES, pairs)
        for (safety, q), cost in zip(pairs, got, strict=True):
            total = 0.0
            for path in paths:
                demand = train + path
                every = levels + [b + safety for b in base]
                quantities = [quantity] * len(train) + [q] * len(path)
                if kind == "sQ":
                    result = simulate(demand, every, quantities, lead, warmup=len(train))
                else:
                    result = simulate_rss(
                        demand, every, quantities, review, lead, warmup=len(train)
                    )
                total += replay_cost(result, RATES).total
            assert cost == pytest.approx(total / len(paths))


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"kind": "RS"}, "applies to 'sQ' and 'RsS'"),
        ({"train_levels": [5.0, 5.0]}, "one level each"),
        ({"train_demand": [], "train_levels": []}, "one level each"),
        ({"paths": []}, "one value per test level"),
        ({"paths": [[1.0]]}, "one value per test level"),
        ({"candidates": [(0.0, 0.0)]}, "order quantity must be positive"),
    ],
)
def test_expected_costs_rejects_bad_input(arguments: dict[str, object], message: str) -> None:
    values: dict[str, object] = {
        "train_demand": [10.0],
        "train_levels": [5.0],
        "train_quantity": 10.0,
        "kind": "sQ",
        "review_period": 1,
        "lead_time": 0.0,
        "base_levels": [5.0, 5.0],
        "paths": [[10.0, 10.0]],
        "rates": RATES,
        "candidates": [(0.0, 10.0)],
    }
    values.update(arguments)
    with pytest.raises(ValueError, match=message):
        expected_costs(**values)  # type: ignore[arg-type]


def test_search_needs_both_grids() -> None:
    with pytest.raises(ValueError, match="at least one value each"):
        search_levels([10.0], [5.0], 10.0, "sQ", 1, 0.0, [5.0], [[1.0]], RATES, [], [10.0])


# --- grids and paths -----------------------------------------------------------------


def test_grids_are_bounded_and_start_with_the_heuristic() -> None:
    grid = safety_grid(7.0, 2.0, 100.0)
    assert grid[0] == 7.0
    assert len(grid) == 1 + len(SAFETY_Z) + len(FORECAST_SHARES)
    assert min(grid) == pytest.approx(-100.0) and max(grid[1:]) == pytest.approx(6.0)
    # z = 0 and a heuristic of 0 are the same value; no forecast, no shares.
    assert safety_grid(0.0, 0.0, 0.0) == (0.0,)
    quantities = quantity_grid(30.0, 10.0)
    assert quantities[0] == 30.0 and 5.0 in quantities and 120.0 in quantities
    assert len(quantities) == len(COVER_PERIODS)  # 30 = 3 periods is already in the grid
    assert quantity_grid(1.0, 0.0) == (1.0,)


def test_demand_paths_add_errors_and_floor_at_zero() -> None:
    paths = demand_paths([10.0, 2.0], [-5.0, 3.0], 50, random.Random(1))
    assert len(paths) == 50 and all(len(p) == 2 for p in paths)
    assert {p[0] for p in paths} == {5.0, 13.0}
    assert {p[1] for p in paths} == {0.0, 5.0}
    with pytest.raises(ValueError, match="at least one error"):
        demand_paths([10.0], [], 5, random.Random(1))


# --- the report ----------------------------------------------------------------------

SERIES = monthly(trend_seasonal_series())


def test_no_test_demand_reaches_the_search() -> None:
    """Changing every test period (zero, or ten times the demand) changes the score
    of the optimised policy, never what the search picked."""
    config = _priced(policy="RsS")
    base = analyze(SERIES, config).out_of_sample
    assert base is not None
    for factor in (0.0, 10.0):
        rows = [["sku", "period", "quantity"]]
        for h in SERIES.skus:
            for i, (p, q) in enumerate(zip(h.periods, h.demand, strict=True)):
                rows.append([h.sku, p, str(q * factor if i >= 36 else q)])
        from inventory_policy_lab import parse_rows

        changed = analyze(parse_rows(rows), config).out_of_sample
        assert changed is not None
        for a, b in zip(base.skus, changed.skus, strict=True):
            assert a.optimized is not None and b.optimized is not None
            assert a.optimized.search == b.optimized.search
            assert a.optimized.test_levels == b.optimized.test_levels
            assert a.optimized.out_of_sample != b.optimized.out_of_sample


def test_the_optimised_replay_is_the_picked_policy_replayed() -> None:
    data = read_demand(SYNTHETIC)
    for policy in ("sQ", "RsS"):
        config = _priced(policy=policy)
        report = analyze(data, config)
        oos = report.out_of_sample
        assert oos is not None and oos.optimize_samples == 20
        for s, history in zip(oos.skus, [h for h in data.skus if h.sku != "SKU-011"], strict=True):
            found = s.optimized
            assert found is not None
            assert found.search.expected_cost <= found.search.heuristic_cost
            normal = s.replay("normal")
            assert found.search.heuristic_safety_stock == normal.safety_stock
            assert found.search.heuristic_order_quantity == normal.order_quantity
            train = len(history.demand) - 12
            shift = found.search.safety_stock - normal.safety_stock
            assert found.test_levels == pytest.approx([normal.reorder_point + shift] * 12)
            from inventory_policy_lab.policy import Policy

            kind_policy = Policy(
                0.95, 0, 0, 0, normal.in_sample.lead_time_periods, 0, 1.0, 0, 0, None, kind=policy
            )
            replayed = replay_policy(
                history.demand,
                kind_policy,
                [normal.order_quantity] * train + [found.order_quantity] * 12,
                [normal.reorder_point] * train + list(found.test_levels),
                warmup=train,
            )
            assert replayed == found.out_of_sample
            assert oos.optimized_sku_cost(s) == replay_cost(replayed, oos.rates_of(s.sku))
            assert found.error_source == "forecast errors" and found.errors >= 2


def test_dynamic_levels_keep_their_forecast_part() -> None:
    config = _priced(policy="RsS", dynamic_levels=True)
    oos = analyze(SERIES, config).out_of_sample
    assert oos is not None
    for s in oos.skus:
        found, normal = s.optimized, s.replay("normal")
        assert found is not None
        shift = found.search.safety_stock - normal.safety_stock
        assert found.test_levels == pytest.approx([lv + shift for lv in normal.test_levels])


def test_too_few_errors_fall_back_to_demand_deviations() -> None:
    from inventory_policy_lab.analysis import _analyze_sku
    from inventory_policy_lab.validation import train_history

    data = read_demand(SYNTHETIC)
    history = data.skus[0]
    train = train_history(history, data.calendar[:12])
    assert train is not None
    config = _priced()
    fitted = _analyze_sku(train, config, "A", 1.0, horizon=12, optimize_inputs=True)
    assert len(fitted.next_forecasts) == 12 and len(fitted.forecast_errors) >= 2
    sparse = replace(fitted, forecast_errors=(1.0,))
    found = _optimized_replay(history, train, sparse, config, CostRates(50, 1, 10))
    assert (found.error_source, found.errors) == ("demand deviations", 12)


def test_report_methods_need_the_search() -> None:
    oos = analyze_file(SYNTHETIC, Config(test_periods=12, order_cost=1.0)).out_of_sample
    assert oos is not None and not oos.optimize_cost
    with pytest.raises(ValueError, match="no cost search"):
        oos.optimized_sku_cost(oos.skus[0])
    with pytest.raises(ValueError, match="no cost search"):
        oos.optimized_totals()


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        ({"optimize_cost": True, "test_periods": 12}, "needs cost rates"),
        (
            {"optimize_cost": True, "test_periods": 12, "order_cost": 1.0, "policy": "RS"},
            "applies to --policy sQ and RsS",
        ),
        ({"optimize_samples": 9}, "optimize samples must be at least 10"),
    ],
)
def test_invalid_settings(settings: dict[str, object], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        Config(**settings).validate()  # type: ignore[arg-type]


def test_json_and_markdown() -> None:
    report = analyze(SERIES, _priced(policy="RsS", rolling_origin=True))
    data = json.loads(render_json(report))
    assert (data["settings"]["optimize_cost"], data["settings"]["optimize_samples"]) == (True, 20)
    optimized = data["out_of_sample"]["optimized"]
    assert optimized["origin"] == "fixed" and optimized["samples"] == 20
    assert optimized["grid"]["cover_periods"] == list(COVER_PERIODS)
    assert [s["sku"] for s in optimized["skus"]] == ["S", "T", "TS"]
    first = optimized["skus"][0]
    assert first["expected_cost"] <= first["heuristic_expected_cost"]
    assert len(first["test_levels"]) == 12
    assert optimized["summary"]["cost"]["total"] == pytest.approx(
        sum(s["cost"]["total"] for s in optimized["skus"]), abs=1e-3
    )
    text = render_markdown(report)
    assert "### Cost-optimised levels (fixed origin, test 2025-01 to 2025-12)" in text
    assert "order quantity Q (S = s + Q)" in text
    assert "| cost-optimised |" in text
    assert "The rolling origin is not searched" in text
    plain = analyze(SERIES, _priced(policy="sQ"))
    plain_text = render_markdown(plain)
    assert "order quantity Q are picked" in plain_text
    assert "The rolling origin is not searched" not in plain_text
    off = json.loads(render_json(analyze(SERIES, _priced(optimize_cost=False))))
    assert "optimize_cost" not in off["settings"]
    assert "optimized" not in off["out_of_sample"]


def test_cli() -> None:
    proc = run_module(
        str(SYNTHETIC),
        "--test-periods",
        "12",
        "--stockout-cost",
        "10",
        "--holding-cost",
        "1",
        "--optimize-cost",
        "--optimize-samples",
        "10",
        "--format",
        "json",
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["out_of_sample"]["optimized"]["samples"] == 10
    bad = run_module(str(SYNTHETIC), "--test-periods", "12", "--optimize-cost")
    assert bad.returncode == 2 and "needs cost rates" in bad.stderr


# --- the README table ----------------------------------------------------------------

# (dataset, policy): fill rate % and total cost of the test year for normal, bootstrap
# and cost-optimised, with --test-periods 12 --trend-seasonal and 50 / 1 / 10.
README_TABLE = {
    ("48", "sQ"): ((99.6, 5474), (97.6, 5125), (88.4, 7766)),
    ("48", "RsS"): ((100.0, 6133), (100.0, 4945), (94.9, 5119)),
    ("24", "sQ"): ((94.4, 21371), (94.6, 19212), (90.6, 18016)),
    ("24", "RsS"): ((99.3, 15576), (98.4, 14157), (86.0, 19102)),
}
# Expected cost on the training paths, summed over SKUs: heuristic, then optimised.
README_EXPECTED = {
    ("48", "sQ"): (5979, 3936),
    ("48", "RsS"): (6324, 3748),
    ("24", "sQ"): (15637, 10418),
    ("24", "RsS"): (14409, 9675),
}
# (R, S) R = 1 at a higher service level: normal fixed-origin fill rate % and cost.
README_RS = {
    ("48", 0.95): (97.4, 4484),
    ("48", 0.98): (98.5, 4474),
    ("48", 0.99): (99.1, 4543),
    ("24", 0.95): (90.9, 17313),
    ("24", 0.98): (92.8, 17522),
    ("24", 0.99): (93.9, 17758),
}


@pytest.mark.parametrize(("dataset", "policy"), list(README_TABLE))
def test_readme_table(dataset: str, policy: str) -> None:
    data = SERIES if dataset == "48" else read_demand(SYNTHETIC)
    oos = analyze(data, _priced(policy=policy, optimize_samples=100)).out_of_sample
    assert oos is not None
    cells = []
    for method in ("normal", "bootstrap"):
        rate = oos.totals(method, "out_of_sample").fill_rate
        assert rate is not None
        cells.append((round(rate * 100, 1), round(oos.cost(method).total)))
    rate = oos.optimized_totals().fill_rate
    assert rate is not None
    cells.append((round(rate * 100, 1), round(oos.optimized_cost().total)))
    assert tuple(cells) == README_TABLE[(dataset, policy)]
    searches = [s.optimized.search for s in oos.skus if s.optimized is not None]
    expected = (
        round(sum(x.heuristic_cost for x in searches)),
        round(sum(x.expected_cost for x in searches)),
    )
    assert expected == README_EXPECTED[(dataset, policy)]


@pytest.mark.parametrize(("dataset", "level"), list(README_RS))
def test_readme_table_of_rs_at_higher_service(dataset: str, level: float) -> None:
    data = SERIES if dataset == "48" else read_demand(SYNTHETIC)
    config = _priced(policy="RS", service_level=level, optimize_cost=False)
    oos = analyze(data, config).out_of_sample
    assert oos is not None
    rate = oos.totals("normal", "out_of_sample").fill_rate
    assert rate is not None
    assert (round(rate * 100, 1), round(oos.cost("normal").total)) == README_RS[(dataset, level)]


def test_optimized_replay_is_exported_from_the_package() -> None:
    import inventory_policy_lab
    from inventory_policy_lab import OptimizedReplay, validation

    assert OptimizedReplay is validation.OptimizedReplay
    assert "OptimizedReplay" in inventory_policy_lab.__all__
    oos = analyze(SERIES, _priced()).out_of_sample
    assert oos is not None
    assert all(isinstance(s.optimized, OptimizedReplay) for s in oos.skus)
