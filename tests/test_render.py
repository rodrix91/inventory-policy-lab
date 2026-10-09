"""Markdown and JSON output."""

from __future__ import annotations

import json
from pathlib import Path

from conftest import EXAMPLES

from inventory_policy_lab import Config, __version__, analyze_file, render_json, render_markdown


def test_json_is_complete_and_rounded() -> None:
    report = analyze_file(EXAMPLES / "worked_example.csv", Config(holdout=2))
    data = json.loads(render_json(report))
    assert data["tool"] == "inventory-policy-lab"
    assert data["version"] == __version__
    assert data["periods"] == 8 and data["first_period"] == "1" and data["last_period"] == "8"
    assert data["summary"]["abc_xyz"]["A"]["X"] == 1
    sku = data["skus"][0]
    assert sku["policy"]["reorder_point"] == 37.9129
    assert sku["policy"]["eoq"] is None
    assert sku["forecast"]["backtest"][1] == {
        "method": "moving_average",
        "mae": 2.0,
        "rmse": 2.8284,
        "bias": -2.0,
        "mase": 0.5,
    }
    assert set(sku["simulation"]) >= {"fill_rate", "stockout_periods", "average_on_hand"}


def test_markdown_sections_class_levels_and_notes() -> None:
    config = Config(holdout=2, class_service_levels={"A": 0.99, "B": 0.9}, sigma="rmse")
    text = render_markdown(analyze_file(EXAMPLES / "worked_example.csv", config))
    for heading in (
        "# Inventory policy report",
        "## ABC-XYZ matrix",
        "## Demand patterns (Syntetos-Boylan)",
        "## Policy per SKU",
        "## Forecast backtest (MASE, last 2 periods)",
        "## Notes",
    ):
        assert heading in text
    assert "Target cycle service level: 95% (by class: A 99%, B 90%)" in text
    assert "RMSE of the picked method" in text
    assert "| W-1 | AX | smooth | moving_average |" in text
    assert "| W-2 | - | - | 2.22 | 1.88 | **1.88** | -2.58 |" in text
    assert "no demand" not in text  # empty category rows are left out


def test_markdown_without_notes_and_with_quantity_basis(tmp_path: Path) -> None:
    rows = "sku,period,quantity,lead_time\n" + "".join(
        f"a,{i},{10 + i % 3},2\n" for i in range(1, 11)
    )
    path = tmp_path / "q.csv"
    path.write_text(rows, encoding="utf-8")
    text = render_markdown(analyze_file(path))
    assert "annual units (no unit_cost column)" in text
    assert "## Notes" not in text


def test_markdown_with_a_sku_without_demand(tmp_path: Path) -> None:
    zero = tmp_path / "zero.csv"
    zero.write_text("sku,period,quantity\n" + "".join(f"z,{i},0\n" for i in range(1, 9)))
    text = render_markdown(analyze_file(zero))
    assert "| no demand | 1 |" in text
    assert "Replayed fill rate, all SKUs: n/a" in text
