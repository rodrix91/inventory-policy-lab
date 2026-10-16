"""Cost rates per SKU (ADR 0014): holding as a yearly rate of unit_cost, cost columns."""

from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import EXAMPLES, run_module, write_csv
from test_rolling import HAND, HAND_CONFIG

from inventory_policy_lab import (
    Config,
    ConfigError,
    CostRates,
    DataError,
    analyze,
    analyze_file,
    parse_rows,
    read_demand,
    render_json,
    render_markdown,
    replay_cost,
)

SYNTHETIC = EXAMPLES / "demand_synthetic.csv"


def _rows(with_columns: bool = True) -> list[list[str]]:
    """SKU A is the hand case of ``test_rolling``; B sells 10 every period.

    A has unit cost 6, order_cost 2 (the last non-empty value; 9 on an earlier
    row) and stockout_cost 3. B has unit cost 12 and no cost values.
    """
    header = ["sku", "period", "quantity", "unit_cost"]
    if with_columns:
        header += ["order_cost", "stockout_cost"]
    rows = [header]
    for i, q in enumerate(HAND["A"]):
        extra = ["9" if i == 0 else ("2" if i == 3 else ""), "3" if i == 6 else ""]
        rows.append(["A", str(i + 1), str(q), "6"] + (extra if with_columns else []))
    for i in range(7):
        rows.append(["B", str(i + 1), "10", "12"] + (["", ""] if with_columns else []))
    return rows


# --- reading the columns -------------------------------------------------------------


def test_cost_columns_are_read_only_when_asked() -> None:
    plain = parse_rows(_rows())
    assert not plain.has_order_cost and not plain.has_stockout_cost
    assert all(h.order_cost is None and h.stockout_cost is None for h in plain.skus)
    read = parse_rows(_rows(), cost_columns=True)
    assert read.has_order_cost and read.has_stockout_cost
    a, b = read.skus
    assert (a.order_cost, a.stockout_cost) == (2.0, 3.0)  # most recent non-empty value
    assert (b.order_cost, b.stockout_cost) == (None, None)
    # The rest of the data is the same with and without the columns.
    assert [h.demand for h in read.skus] == [h.demand for h in plain.skus]


def test_one_cost_column_is_enough(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "d.csv", "sku,period,quantity,stockout_cost\nA,1,5,7\n")
    data = read_demand(path, cost_columns=True)
    assert not data.has_order_cost and data.has_stockout_cost
    assert data.skus[0].stockout_cost == 7.0


@pytest.mark.parametrize(
    ("cell", "message"),
    [("-1", "negative order_cost -1"), ("abc", "order_cost 'abc' is not a number")],
)
def test_bad_cost_values_are_data_errors(cell: str, message: str) -> None:
    rows = [["sku", "period", "quantity", "order_cost"], ["A", "1", "5", cell]]
    with pytest.raises(DataError, match=message):
        parse_rows(rows, cost_columns=True)
    assert parse_rows(rows).skus[0].order_cost is None  # ignored without the option


# --- the rates of one SKU ------------------------------------------------------------


def test_sku_cost_rates_by_hand() -> None:
    a, b = parse_rows(_rows(), cost_columns=True).skus
    config = Config(
        test_periods=3, order_cost=5, stockout_cost=4, holding_cost_rate=0.5, cost_columns=True
    )
    # Holding 0.5 a year x unit cost / 12 periods: A 6 -> 0.25, B 12 -> 0.5.
    assert config.sku_cost_rates(a) == CostRates(order=2, holding=0.25, stockout=3)
    assert config.sku_cost_rates(b) == CostRates(order=5, holding=0.5, stockout=4)
    # Without the columns, the shared order and stockout costs.
    no_columns = replace(config, cost_columns=False)
    assert no_columns.sku_cost_rates(a) == CostRates(order=5, holding=0.25, stockout=4)
    # Without the rate, the shared holding cost.
    shared = replace(config, holding_cost_rate=None, holding_cost=1.5)
    assert shared.sku_cost_rates(a) == CostRates(order=2, holding=1.5, stockout=3)
    # Weekly periods make the same yearly rate cheaper per period.
    weekly = replace(config, periods_per_year=52)
    assert weekly.sku_cost_rates(b).holding == pytest.approx(0.5 * 12 / 52)


def test_per_sku_rates_need_a_rate_and_a_unit_cost() -> None:
    a, _ = parse_rows(_rows(), cost_columns=True).skus
    with pytest.raises(ValueError, match="no cost rates"):
        Config().sku_cost_rates(a)
    config = Config(test_periods=3, holding_cost_rate=0.25)
    with pytest.raises(ValueError, match="has no unit cost"):
        config.sku_cost_rates(replace(a, unit_cost=None))


def test_a_rate_or_the_columns_alone_turn_the_costs_on() -> None:
    assert Config(test_periods=3, holding_cost_rate=0.25).cost_rates == CostRates(0, 0, 0)
    assert Config(test_periods=3, cost_columns=True).cost_rates == CostRates(0, 0, 0)
    assert Config(test_periods=3).per_sku_costs is False
    assert Config(test_periods=3, order_cost=1).per_sku_costs is False


# --- settings ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        ({"holding_cost_rate": -0.1, "test_periods": 3}, "holding cost rate must be a finite"),
        ({"holding_cost_rate": math.nan, "test_periods": 3}, "holding cost rate must be a finite"),
        ({"holding_cost_rate": 0.25}, "need test periods"),
        ({"cost_columns": True}, "need test periods"),
        (
            {"holding_cost_rate": 0.25, "holding_cost": 1.0, "test_periods": 3},
            "not both",
        ),
    ],
)
def test_invalid_settings(settings: dict[str, object], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        Config(**settings).validate()  # type: ignore[arg-type]


def test_the_rate_needs_a_unit_cost_column() -> None:
    data = parse_rows([["sku", "period", "quantity"]] + [["A", str(i), "5"] for i in range(1, 9)])
    with pytest.raises(DataError, match="holding cost rate needs a unit_cost column"):
        analyze(data, Config(test_periods=2, holdout=2, holding_cost_rate=0.25))


def test_the_columns_option_needs_a_column_read_with_it() -> None:
    config = replace(HAND_CONFIG, cost_columns=True)
    with pytest.raises(DataError, match="need an order_cost or stockout_cost column"):
        analyze(parse_rows(_rows()), config)  # read without cost_columns
    analyze(parse_rows(_rows(), cost_columns=True), config)


# --- the report ----------------------------------------------------------------------


def _hand_report() -> tuple[Config, object]:
    config = replace(
        HAND_CONFIG,
        rolling_origin=False,
        order_cost=5.0,
        stockout_cost=4.0,
        holding_cost_rate=0.5,
        cost_columns=True,
    )
    return config, analyze(parse_rows(_rows(), cost_columns=True), config)


def test_out_of_sample_cost_with_per_sku_rates_by_hand() -> None:
    """A: the fixed replay of ``test_costs.test_out_of_sample_cost_by_hand`` (8 orders,
    nothing on hand at any end, 20 short) at its own 2 per order and 3 per unit short:
    16 + 0 + 60 = 76.

    B: s = 10 (forecast 10, no variation, L = 0), Q = 10; every test period ends
    with 10 on hand and orders once: 3 orders, 30 unit-periods, nothing short. At
    the shared 5 per order and 0.5 x 12 / 12 = 0.5 per unit-period: 15 + 15 = 30.
    """
    _, report = _hand_report()
    oos = report.out_of_sample  # type: ignore[attr-defined]
    assert oos is not None and oos.costs == CostRates(5, 0, 4)
    a, b = oos.skus
    assert oos.rates_of("A") == CostRates(2, 0.25, 3)
    cost_a = oos.sku_cost(a, "normal")
    assert (cost_a.orders, cost_a.unit_periods, cost_a.units_short) == (8, 0, 20)
    assert (cost_a.ordering, cost_a.stockout, cost_a.total) == (16, 60, 76)
    cost_b = oos.sku_cost(b, "normal")
    assert (cost_b.orders, cost_b.unit_periods, cost_b.units_short) == (3, 30, 0)
    assert (cost_b.ordering, cost_b.holding, cost_b.total) == (15, 15, 30)
    assert oos.cost("normal").total == 106
    for s in oos.skus:
        assert oos.sku_cost(s, "bootstrap") == replay_cost(
            s.replay("bootstrap").out_of_sample, oos.rates_of(s.sku)
        )


def test_rates_of_falls_back_to_the_shared_rates() -> None:
    oos = analyze(parse_rows(_rows()), replace(HAND_CONFIG, order_cost=5.0)).out_of_sample
    assert oos is not None and oos.sku_rates == {}
    assert oos.rates_of("A") == CostRates(5, 0, 0)
    bare = analyze(parse_rows(_rows()), HAND_CONFIG).out_of_sample
    assert bare is not None
    with pytest.raises(ValueError, match="no cost rates"):
        bare.rates_of("A")


def test_a_rate_equal_to_the_shared_cost_gives_the_same_report() -> None:
    """One SKU with unit cost 6: a yearly rate of 2 is 1 per unit and period."""
    rows = [r[:4] for r in _rows(with_columns=False) if r[0] != "B"]
    data = parse_rows(rows)
    shared = analyze(data, replace(HAND_CONFIG, holding_cost=1.0)).out_of_sample
    rated = analyze(data, replace(HAND_CONFIG, holding_cost_rate=2.0)).out_of_sample
    assert shared is not None and rated is not None
    for origin in ("fixed", "rolling"):
        assert rated.cost("normal", origin) == shared.cost("normal", origin)


def test_json_and_markdown_with_per_sku_rates() -> None:
    _, report = _hand_report()
    data = json.loads(render_json(report))  # type: ignore[arg-type]
    settings = data["settings"]
    assert (settings["holding_cost_rate"], settings["cost_columns"]) == (0.5, True)
    costs = data["out_of_sample"]["costs"]
    assert costs["rates"] == {
        "order": 5.0,
        "holding": None,
        "stockout": 4.0,
        "holding_rate_of_unit_cost": 0.5,
        "cost_columns": True,
    }
    assert costs["skus"][0]["rates"] == {"order": 2.0, "holding": 0.25, "stockout": 3.0}
    assert costs["skus"][1]["rates"] == {"order": 5.0, "holding": 0.5, "stockout": 4.0}
    assert costs["summary"]["normal"]["fixed"]["total"] == 106
    text = render_markdown(report)  # type: ignore[arg-type]
    assert "5 per order placed (or the SKU's order_cost)" in text
    assert "0.5 a year of the SKU's unit_cost per unit on hand" in text
    assert "4 per unit of demand not served from stock in its period (or the SKU's" in text
    assert "| SKU | Per order | Per unit held a period | Per unit short |" in text
    assert "| A | 2.00 | 0.2500 | 3.00 |" in text
    assert "| B | 5.00 | 0.5000 | 4.00 |" in text


def test_columns_alone_keep_the_shared_holding_wording() -> None:
    config = replace(HAND_CONFIG, holding_cost=1.0, cost_columns=True)
    report = analyze(parse_rows(_rows(), cost_columns=True), config)
    data = json.loads(render_json(report))
    assert "holding_cost_rate" not in data["settings"]
    assert data["out_of_sample"]["costs"]["rates"]["holding"] == 1.0
    assert "holding_rate_of_unit_cost" not in data["out_of_sample"]["costs"]["rates"]
    assert "1 per unit on hand at the end of a period" in render_markdown(report)


def test_shared_rates_keep_the_080_report() -> None:
    report = analyze_file(SYNTHETIC, Config(test_periods=12, order_cost=50, holding_cost=1))
    data = json.loads(render_json(report))
    assert set(data["settings"]) >= {"order_cost", "holding_cost", "stockout_cost"}
    assert "holding_cost_rate" not in data["settings"]
    assert "cost_columns" not in data["settings"]
    assert set(data["out_of_sample"]["costs"]["rates"]) == {"order", "holding", "stockout"}
    assert all("rates" not in s for s in data["out_of_sample"]["costs"]["skus"])
    assert "Per unit held a period" not in render_markdown(report)


def test_analyze_file_reads_the_columns_only_with_the_option(tmp_path: Path) -> None:
    path = tmp_path / "d.csv"
    path.write_text("\n".join(",".join(r) for r in _rows()) + "\n", encoding="utf-8")
    assert analyze_file(path, HAND_CONFIG).data.has_order_cost is False
    report = analyze_file(path, replace(HAND_CONFIG, cost_columns=True))
    assert report.data.has_order_cost


# --- command line --------------------------------------------------------------------


def test_cli_holding_rate_and_cost_columns(tmp_path: Path) -> None:
    path = tmp_path / "d.csv"
    path.write_text("\n".join(",".join(r) for r in _rows()) + "\n", encoding="utf-8")
    common = ["--test-periods", "3", "--holdout", "2", "--lead-time", "0", "--format", "json"]
    proc = run_module(
        str(path),
        *common,
        "--order-cost",
        "5",
        "--stockout-cost",
        "4",
        "--holding-cost-rate",
        "0.5",
        "--cost-columns",
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["out_of_sample"]["costs"]["summary"]["normal"]["fixed"]["total"] == 106
    both = run_module(str(path), *common, "--holding-cost", "1", "--holding-cost-rate", "0.5")
    assert both.returncode == 2 and "not both" in both.stderr
    no_unit_cost = run_module(
        str(EXAMPLES / "worked_example.csv"), "--test-periods", "2", "--holdout", "2"
    )
    assert no_unit_cost.returncode == 0


# --- the README table ----------------------------------------------------------------

README_TABLE = {
    ("sQ", 1): (13662, 9660, 14190, 10361),
    ("RS", 1): (12558, 8449, 13254, 8473),
    ("RS", 3): (10118, 7891, 9478, 7124),
    ("RsS", 1): (6941, 6546, 6923, 5903),
    ("RsS", 3): (8232, 7526, 8014, 7225),
}


@pytest.mark.parametrize(("policy", "review"), list(README_TABLE))
def test_readme_table_of_holding_priced_per_sku(policy: str, review: int) -> None:
    config = Config(
        test_periods=12,
        trend_seasonal=True,
        dynamic_levels=True,
        bootstrap_source="residuals",
        rolling_origin=True,
        policy=policy,
        review_period=review,
        order_cost=50,
        stockout_cost=10,
        holding_cost_rate=0.25,
    )
    oos = analyze_file(SYNTHETIC, config).out_of_sample
    assert oos is not None
    totals = tuple(
        round(oos.cost(method, origin).total)
        for method in ("normal", "bootstrap")
        for origin in ("fixed", "rolling")
    )
    assert totals == README_TABLE[(policy, review)]
