"""Reject Python-specific numeric separators in exported inventory CSVs."""

from __future__ import annotations

from pathlib import Path

import pytest

from inventory_policy_lab import DataError, parse_rows, read_demand
from inventory_policy_lab.cli import main


HEADER = [
    "sku", "period", "quantity", "unit_cost", "lead_time", "order_cost", "stockout_cost"
]
VALUES = ["A", "1", "3", "2", "1", "4", "5"]


@pytest.mark.parametrize(
    "column",
    ["quantity", "unit_cost", "lead_time", "order_cost", "stockout_cost"],
)
@pytest.mark.parametrize("value", ["1_000", "1e1_0"])
def test_python_only_underscores_are_not_valid_csv_numbers(column: str, value: str) -> None:
    record = VALUES.copy()
    record[HEADER.index(column)] = value
    with pytest.raises(DataError) as caught:
        parse_rows([HEADER, record], cost_columns=True)
    assert str(caught.value) == f"line 2: {column} '{value}' is not a number"
    assert caught.value.exit_code == 4


def test_valid_exponent_notation_and_cost_fields_remain_supported() -> None:
    data = parse_rows(
        [HEADER, ["A", "1", "1e2", "2.5e1", "1e1", "5e1", "6e1"]],
        cost_columns=True,
    )
    sku = data.skus[0]
    assert sku.demand == (100.0,)
    assert sku.unit_cost == 25.0
    assert sku.lead_times == (10.0,)
    assert sku.order_cost == 50.0
    assert sku.stockout_cost == 60.0


def test_file_reader_rejects_underscore_quantity(tmp_path: Path) -> None:
    source = tmp_path / "erp.csv"
    source.write_text("sku,period,quantity\\nA,1,1_000\\n", encoding="utf-8")
    with pytest.raises(DataError, match="line 2: quantity '1_000' is not a number"):
        read_demand(source)


def test_cli_does_not_replace_existing_report_when_export_is_invalid(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "supplier.csv"
    source.write_text("sku,period,quantity\\nA,1,1e1_0\\n", encoding="utf-8")
    output = tmp_path / "verified.json"
    original = '{"status":"verified"}\\n'
    output.write_text(original, encoding="utf-8")
    assert main([str(source), "--format", "json", "--output", str(output)]) == 4
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "quantity '1e1_0' is not a number" in captured.err
    assert "Traceback" not in captured.err
    assert output.read_text(encoding="utf-8") == original
