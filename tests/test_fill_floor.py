"""Fill-rate floor of the cost search (ADR 0016)."""

from __future__ import annotations

import json

import pytest
from conftest import EXAMPLES, run_module
from test_smoothing import monthly, trend_seasonal_series

from inventory_policy_lab import (
    Config,
    ConfigError,
    CostRates,
    analyze,
    parse_rows,
    read_demand,
    render_json,
    render_markdown,
)
from inventory_policy_lab.optimize import (
    CostSearch,
    expected_costs,
    expected_outcomes,
    search_levels,
)
from inventory_policy_lab.render import _fill_pair

SYNTHETIC = EXAMPLES / "demand_synthetic.csv"
SERIES = monthly(trend_seasonal_series())
CHEAP_SHORTAGE = CostRates(order=2, holding=1, stockout=0.5)
PATHS = [[10.0, 10.0], [0.0, 0.0]]


def _search(safety: list[float], floor: float | None, step: float = 0.0) -> CostSearch:
    """(s, Q), L = 0, Q = 10: one training period of 10 at level 5, then ``PATHS``."""
    return search_levels(
        [10.0],
        [5.0],
        10.0,
        "sQ",
        1,
        0.0,
        [5.0, 5.0],
        PATHS,
        CHEAP_SHORTAGE,
        safety,
        [10.0],
        refine_step=step,
        fill_floor=floor,
    )


def _priced(**settings: object) -> Config:
    base: dict[str, object] = {
        "test_periods": 12,
        "trend_seasonal": True,
        "order_cost": 50.0,
        "holding_cost": 1.0,
        "stockout_cost": 10.0,
        "optimize_cost": True,
        "optimize_samples": 20,
        "optimize_fill_floor": 0.95,
    }
    base.update(settings)
    return Config(**base)  # type: ignore[arg-type]


# --- expected fill rate, by hand ----------------------------------------------------


def test_expected_outcomes_by_hand() -> None:
    """The cases of ``test_expected_costs_by_hand`` with a stockout cost of 0.5.

    (SS 0): path [10, 10] costs 4 + 10 = 14 and serves all 20; path [0, 0] costs 30
    (15 on hand twice) and has no demand. Mean 22, fill rate 20 / 20.
    (SS -5): path [10, 10] costs 2 + 5 + 2.5 = 9.5 and serves 15 of 20; path [0, 0]
    costs 30. Mean 19.75, fill rate 15 / 20.
    """
    candidates = [(0.0, 10.0), (-5.0, 10.0)]
    args = ([10.0], [5.0], 10.0, "sQ", 1, 0.0, [5.0, 5.0], PATHS, CHEAP_SHORTAGE, candidates)
    assert expected_outcomes(*args) == [(22.0, 1.0), (19.75, 0.75)]
    assert expected_costs(*args) == [22.0, 19.75]


def test_paths_without_demand_have_a_full_fill_rate() -> None:
    outcomes = expected_outcomes(
        [0.0], [5.0], 10.0, "sQ", 1, 0.0, [5.0], [[0.0]], CHEAP_SHORTAGE, [(0.0, 10.0)]
    )
    assert outcomes[0][1] == 1.0


# --- the search with a floor --------------------------------------------------------


def test_without_a_floor_the_cheapest_pair_wins() -> None:
    found = _search([-5.0, 0.0], None)
    assert (found.safety_stock, found.expected_cost) == (-5.0, 19.75)
    assert (found.fill_floor, found.expected_fill, found.heuristic_fill) == (None, None, None)
    assert (found.feasible, found.fell_back) == (0, False)


def test_the_floor_rules_out_the_cheaper_pair() -> None:
    found = _search([-5.0, 0.0], 0.9)
    assert (found.safety_stock, found.expected_cost) == (0.0, 22.0)
    assert (found.heuristic_safety_stock, found.heuristic_cost) == (-5.0, 19.75)
    assert (found.expected_fill, found.heuristic_fill) == (1.0, 0.75)
    assert (found.fill_floor, found.feasible, found.fell_back) == (0.9, 1, False)


def test_a_floor_met_exactly_is_accepted() -> None:
    assert _search([-5.0, 0.0], 0.75).safety_stock == -5.0


def test_no_pair_meets_the_floor_keeps_the_heuristic_without_refining() -> None:
    found = _search([-5.0, -10.0], 1.0, step=1.0)
    assert (found.safety_stock, found.order_quantity) == (-5.0, 10.0)
    assert found.expected_cost == found.heuristic_cost == 19.75
    assert (found.fell_back, found.feasible, found.candidates) == (True, 0, 2)
    assert found.expected_fill == found.heuristic_fill == 0.75


def test_the_refinement_respects_the_floor() -> None:
    """Around SS 0 the steps -1 to -4 (level 4 to 1) leave 5 units short on path [10, 10]
    and are cheaper (19.75) but below the floor; +1 to +4 serve everything at the
    same cost, so they are accepted but do not replace the pick."""
    found = _search([-5.0, 0.0], 0.9, step=1.0)
    assert (found.safety_stock, found.expected_cost) == (0.0, 22.0)
    assert (found.candidates, found.feasible) == (10, 5)


def test_a_refined_pair_can_win_under_the_floor() -> None:
    """Holding cost 1, stockout cost 100, L = 1: more stock serves more, so the
    cheapest pair meeting the floor sits between two grid values."""
    rates = CostRates(order=1, holding=1, stockout=100)
    args = ([10.0, 10.0], [10.0, 10.0], 10.0, "sQ", 1, 1.0, [10.0, 10.0, 10.0])
    paths = [[10.0, 14.0, 10.0], [10.0, 6.0, 10.0]]
    found = search_levels(*args, paths, rates, [0.0, 16.0], [10.0], 1.0, 0.9)
    assert (found.fell_back, found.candidates, found.feasible) == (False, 10, 9)
    assert (found.safety_stock, found.expected_cost) == (12.0, 215.5)
    assert found.expected_fill == pytest.approx(14 / 15)
    assert found.heuristic_fill == pytest.approx(13 / 15)


# --- the report ---------------------------------------------------------------------


def test_every_pick_meets_the_floor_or_falls_back() -> None:
    for data in (SERIES, read_demand(SYNTHETIC)):
        for policy in ("sQ", "RsS"):
            for floor in (0.95, 1.0):
                oos = analyze(data, _priced(policy=policy, optimize_fill_floor=floor)).out_of_sample
                assert oos is not None and oos.optimize_fill_floor == floor
                for s in oos.skus:
                    assert s.optimized is not None
                    search = s.optimized.search
                    assert search.fill_floor == floor and search.expected_fill is not None
                    if search.fell_back:
                        assert search.safety_stock == search.heuristic_safety_stock
                        assert search.order_quantity == search.heuristic_order_quantity
                    else:
                        assert search.expected_fill >= floor
                        assert search.feasible >= 1


def test_without_the_floor_the_search_is_unchanged() -> None:
    plain = analyze(SERIES, _priced(optimize_fill_floor=None)).out_of_sample
    assert plain is not None and plain.optimize_fill_floor is None
    for s in plain.skus:
        assert s.optimized is not None
        assert s.optimized.search.fill_floor is None and s.optimized.search.feasible == 0


def test_no_test_demand_reaches_the_floor() -> None:
    config = _priced(policy="RsS")
    base = analyze(SERIES, config).out_of_sample
    assert base is not None
    rows = [["sku", "period", "quantity"]]
    for h in SERIES.skus:
        for i, (p, q) in enumerate(zip(h.periods, h.demand, strict=True)):
            rows.append([h.sku, p, str(0.0 if i >= 36 else q)])
    changed = analyze(parse_rows(rows), config).out_of_sample
    assert changed is not None
    for a, b in zip(base.skus, changed.skus, strict=True):
        assert a.optimized is not None and b.optimized is not None
        assert a.optimized.search == b.optimized.search


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        ({"optimize_cost": False}, "needs --optimize-cost"),
        ({"optimize_fill_floor": 0.0}, r"must be in \(0, 1\]"),
        ({"optimize_fill_floor": 1.5}, r"must be in \(0, 1\]"),
        ({"optimize_fill_floor": float("nan")}, r"must be in \(0, 1\]"),
    ],
)
def test_invalid_floor(settings: dict[str, object], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        _priced(**settings).validate()


def test_json_and_markdown() -> None:
    report = analyze(SERIES, _priced(policy="RsS"))
    data = json.loads(render_json(report))
    assert data["settings"]["optimize_fill_floor"] == 0.95
    optimized = data["out_of_sample"]["optimized"]
    assert optimized["fill_floor"] == 0.95
    assert optimized["summary"]["fell_back"] == 0
    first = optimized["skus"][0]
    assert first["expected_fill_rate"] >= 0.95 and first["fell_back"] is False
    assert {"heuristic_expected_fill_rate", "feasible"} <= set(first)
    assert list(optimized) == ["origin", "samples", "grid", "fill_floor", "summary", "skus"]
    text = render_markdown(report)
    assert "Fill-rate floor: only pairs whose expected fill rate" in text
    assert "at least 95.0% are accepted" in text and "(0 of 3 SKU(s))" in text
    assert "Expected fill rate on training paths, normal / optimised" in text
    off = analyze(SERIES, _priced(policy="RsS", optimize_fill_floor=None))
    off_data = json.loads(render_json(off))
    assert "optimize_fill_floor" not in off_data["settings"]
    assert "fill_floor" not in off_data["out_of_sample"]["optimized"]
    assert "expected_fill_rate" not in off_data["out_of_sample"]["optimized"]["skus"][0]
    assert "Fill-rate floor" not in render_markdown(off)


def test_fill_pair_marks_a_fallback() -> None:
    search = CostSearch(1, 2, 3, 1, 2, 3, 1, 10, 0.99, 0.9, 0.9, 0, True)
    assert _fill_pair(search) == "90.0% / 90.0% (none met the floor)"
    assert _fill_pair(CostSearch(1, 2, 3, 1, 2, 3, 1, 10, 0.9, 0.95, 0.9, 1)) == "90.0% / 95.0%"


def test_cli() -> None:
    common = ["--test-periods", "12", "--stockout-cost", "10", "--holding-cost", "1"]
    proc = run_module(
        str(SYNTHETIC),
        *common,
        "--optimize-cost",
        "--optimize-samples",
        "10",
        "--optimize-fill-floor",
        "0.9",
        "--format",
        "json",
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["out_of_sample"]["optimized"]["fill_floor"] == 0.9
    bad = run_module(str(SYNTHETIC), *common, "--optimize-cost", "--optimize-fill-floor", "2")
    assert bad.returncode == 2 and "fill-rate floor must be in (0, 1]" in bad.stderr
    alone = run_module(str(SYNTHETIC), *common, "--optimize-fill-floor", "0.9")
    assert alone.returncode == 2 and "needs --optimize-cost" in alone.stderr
