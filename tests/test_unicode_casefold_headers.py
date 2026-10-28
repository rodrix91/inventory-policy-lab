"""Full Unicode casefold protects case-equivalent consumed ERP headers."""

from __future__ import annotations

from pathlib import Path

import pytest

from inventory_policy_lab import DataError, parse_rows
from inventory_policy_lab.cli import main


@pytest.mark.parametrize("header", ["ſku", " ſKU ", "ſKU"])
def test_unicode_case_equivalent_sku_header_is_recognized(header: str) -> None:
    data = parse_rows([[header, "period", "quantity"], ["A", "1", "5"]])
    assert data.rows == 1
    assert data.skus[0].sku == "A"
    assert data.skus[0].demand == (5.0,)


@pytest.mark.parametrize(
    ("header", "field"),
    [
        (["sku", "ſku", "period", "quantity"], "sku"),
        (["ſku", " SKU ", "period", "quantity"], "sku"),
        (["sku", "period", "quantity", "ſtockout_coſt", "stockout_cost"], "stockout_cost"),
    ],
)
def test_unicode_case_equivalent_consumed_duplicates_fail_closed(
    header: list[str], field: str
) -> None:
    row = ["A", "1", "5", "10", "20"][: len(header)]
    with pytest.raises(DataError, match=f"ambiguous {field} columns") as info:
        parse_rows([header, row], cost_columns=True)
    assert info.value.exit_code == 4
    assert "keep only one" in str(info.value)


def test_unicode_casefold_optional_cost_alias_remains_opt_in() -> None:
    header = ["sku", "period", "quantity", "ſtockout_coſt"]
    row = ["A", "1", "5", "7"]
    without_costs = parse_rows([header, row])
    assert not without_costs.has_stockout_cost
    assert without_costs.skus[0].stockout_cost is None

    with_costs = parse_rows([header, row], cost_columns=True)
    assert with_costs.has_stockout_cost
    assert with_costs.skus[0].stockout_cost == 7.0


def test_casefold_ambiguous_cli_input_preserves_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "duplicate-erp.csv"
    source.write_text("sku,ſku,period,quantity\nA,B,1,5\n", encoding="utf-8")
    report = tmp_path / "verified-report.json"
    previous = '{"already":"verified"}\n'
    report.write_text(previous, encoding="utf-8")
    assert main([str(source), "--format", "json", "--output", str(report)]) == 4
    captured = capsys.readouterr()
    assert "ambiguous sku columns" in captured.err
    assert "column 1" in captured.err and "column 2" in captured.err
    assert captured.out == ""
    assert "Traceback" not in captured.err
    assert report.read_text(encoding="utf-8") == previous
