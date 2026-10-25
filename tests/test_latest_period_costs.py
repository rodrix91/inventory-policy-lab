"""Cost cells come from the latest chronological period, even in unsorted CSV exports."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import run_module, write_csv

from inventory_policy_lab import parse_rows, read_demand


@pytest.mark.parametrize(
    ("older", "newer"),
    [
        ("2", "10"),
        ("2025-12", "2026-01"),
        ("2026-01-31", "2026-02-01"),
    ],
)
def test_latest_nonempty_cost_is_chronological_not_last_csv_row(older: str, newer: str) -> None:
    rows = [
        ["sku", "period", "quantity", "unit_cost", "order_cost", "stockout_cost"],
        ["A", newer, "4", "30", "70", "90"],
        ["A", older, "2", "5", "6", "7"],
        ["A", newer, "1", "", "", ""],
        ["B", older, "3", "8", "12", "13"],
        ["B", newer, "3", "18", "22", "23"],
        ["B", older, "1", "1", "2", "3"],
    ]
    data = parse_rows(rows, cost_columns=True)
    a, b = data.skus
    assert (a.unit_cost, a.order_cost, a.stockout_cost) == (30, 70, 90)
    assert (b.unit_cost, b.order_cost, b.stockout_cost) == (18, 22, 23)
    assert (a.demand[-1], b.demand[-1]) == (5, 3)
    assert data.rows == 6


def test_each_cost_field_selects_its_own_latest_nonempty_period() -> None:
    rows = [
        ["sku", "period", "quantity", "unit_cost", "order_cost", "stockout_cost"],
        ["A", "2026-04", "2", "44", "", ""],
        ["A", "2026-03", "1", "", "33", ""],
        ["A", "2026-02", "2", "", "", "22"],
        ["A", "2026-01", "1", "1", "2", "3"],
        ["B", "2026-01", "1", "9", "10", "11"],
    ]
    read = parse_rows(rows, cost_columns=True)
    a, b = read.skus
    assert (a.unit_cost, a.order_cost, a.stockout_cost) == (44, 33, 22)
    assert (b.unit_cost, b.order_cost, b.stockout_cost) == (9, 10, 11)
    baseline = parse_rows(rows)
    assert (baseline.skus[0].unit_cost, baseline.skus[0].order_cost) == (44, None)
    assert baseline.skus[0].stockout_cost is None


def test_ties_resolve_to_last_nonempty_row_even_with_integer_spelling_variants() -> None:
    rows = [
        ["sku", "period", "quantity", "unit_cost", "order_cost", "stockout_cost"],
        ["A", "002", "1", "20", "25", "30"],
        ["A", "1", "1", "1", "2", "3"],
        ["A", "2", "1", "21", "", "31"],
        ["A", "02", "1", "", "26", ""],
        ["A", "01", "1", "2", "4", "5"],
    ]
    data = parse_rows(rows, cost_columns=True)
    a = data.skus[0]
    assert data.calendar == ("1", "2")
    assert a.demand == (2, 3)
    assert (a.unit_cost, a.order_cost, a.stockout_cost) == (21, 26, 31)


def test_cli_prices_replay_with_latest_period_rates_from_unsorted_csv(tmp_path: Path) -> None:
    rows = ["sku,period,quantity,unit_cost,order_cost,stockout_cost", "A,10,5,40,7,9"]
    rows.extend(f"A,{i},5,,," for i in range(2, 10))
    rows.append("A,1,5,2,99,50")
    path = write_csv(tmp_path / "unsorted.csv", "\n".join(rows) + "\n")
    file_data = read_demand(path, cost_columns=True)
    assert (file_data.skus[0].unit_cost, file_data.skus[0].order_cost) == (40, 7)

    result = run_module(
        str(path),
        "--holdout",
        "2",
        "--test-periods",
        "2",
        "--format",
        "json",
        "--cost-columns",
        "--holding-cost-rate",
        "0.25",
        "--order-cost",
        "5",
        "--stockout-cost",
        "1",
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["skus"][0]["unit_cost"] == 40
    rates = report["out_of_sample"]["costs"]["skus"][0]["rates"]
    assert rates["order"] == 7
    assert rates["holding"] == round(40 * 0.25 / 12, 4)  # JSON cost rates use 4 decimals
    assert rates["stockout"] == 9
