"""Keep the documented regional Excel fixture executable and honest."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from inventory_policy_lab import DataError, read_demand
from inventory_policy_lab.cli import main

EXCEL_SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "regional-excel.csv"


def test_regional_excel_sample_has_expected_demand_history() -> None:
    data = read_demand(EXCEL_SAMPLE, delimiter="semicolon")
    assert data.rows == 24
    assert data.period_kind == "month"
    assert len(data.calendar) == 12
    assert {item.sku for item in data.skus} == {"CAFE-01", "TEA-02"}


def test_regional_excel_sample_requires_matching_explicit_delimiter() -> None:
    with pytest.raises(DataError, match="pass --delimiter semicolon instead of comma"):
        read_demand(EXCEL_SAMPLE)


def test_readme_regional_excel_cli_command_generates_json(tmp_path: Path) -> None:
    target = tmp_path / "inventory-report.json"
    args = [str(EXCEL_SAMPLE), "--delimiter", "semicolon", "--format", "json", "-o", str(target)]
    assert main(args) == 0
    result = json.loads(target.read_text(encoding="utf-8"))
    assert result["rows"] == 24
    assert result["summary"]["skus"] == 2
