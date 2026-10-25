"""Ambiguous columns in an ERP extract must never silently change demand inputs."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from inventory_policy_lab import DataError, parse_rows

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("header", "field", "expected_column"),
    [
        ("sku, SKU ,period,quantity", "sku", 2),
        ("sku,period,date,quantity", "period", 3),
        ("sku,period,quantity,qty", "quantity", 4),
        ("sku,period,demand,quantity", "quantity", 4),
        ("sku,period,quantity, QUANTITY ", "quantity", 4),
        ("sku,period,quantity,unit_cost, UNIT_COST ", "unit_cost", 5),
        ("sku,period,quantity,lead_time, LEAD_TIME ", "lead_time", 5),
    ],
)
def test_ambiguous_consumed_columns_fail_closed(
    header: str, field: str, expected_column: int
) -> None:
    columns = header.split(",")
    with pytest.raises(DataError, match=f"ambiguous {field} columns") as info:
        parse_rows([columns, ["A", "1", "12", "13", "14"][: len(columns)]])
    assert info.value.exit_code == 4
    assert f"column {expected_column}" in str(info.value)
    assert "keep only one" in str(info.value)


@pytest.mark.parametrize("cost", ["order_cost", "stockout_cost"])
def test_cost_column_duplicates_rejected_only_when_opted_in(cost: str) -> None:
    header = ["sku", "period", "quantity", cost, cost.upper()]
    body = ["A", "1", "12", "10", "20"]
    permissive = parse_rows([header, body], cost_columns=False)
    assert permissive.skus[0].demand == (12.0,)
    assert not permissive.has_order_cost and not permissive.has_stockout_cost
    with pytest.raises(DataError, match=f"ambiguous {cost} columns"):
        parse_rows([header, body], cost_columns=True)


def test_distinct_aliases_remain_valid_with_unrelated_extra_columns() -> None:
    report = parse_rows(
        [
            [" SKU ", "Date", "Qty", "notes", "notes"],
            ["A", "1", "12", "first", "second"],
            ["A", "2", "13", "third", "fourth"],
        ]
    )
    assert report.skus[0].demand == (12.0, 13.0)
    assert report.rows == 2


def test_cli_ambiguous_quantity_preserves_existing_output(tmp_path: Path) -> None:
    source = tmp_path / "orders.csv"
    source.write_text("sku,period,quantity,qty\nA,1,12,999\n", encoding="utf-8")
    output = tmp_path / "policy.json"
    output.write_text("existing verified report\n", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    run = subprocess.run(
        [sys.executable, "-m", "inventory_policy_lab", str(source), "--format", "json", "--output", str(output)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 4
    assert "ambiguous quantity columns" in run.stderr
    assert "column 3" in run.stderr and "column 4" in run.stderr
    assert not run.stdout
    assert output.read_text(encoding="utf-8") == "existing verified report\n"
