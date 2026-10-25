"""Prevent ABC value overflow from producing false inventory priorities."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from conftest import run_module, write_csv

from inventory_policy_lab import Config, DataError, abc_classes, analyze, parse_rows


def test_finite_abc_values_with_infinite_total_keep_correct_classes() -> None:
    values = {"D": 1e308, "B": 1e308, "A": 1e308, "C": 1e308}
    # Total 4e308 is not representable as a float. Each SKU contributes 25%.
    # Before each SKU: A=0%, B=25%, C=50%, D=75%.
    assert abc_classes(values, a=0.30, b=0.70) == {
        "A": "A",
        "B": "A",
        "C": "B",
        "D": "C",
    }


def test_abc_normal_values_and_empty_or_zero_data_remain_unchanged() -> None:
    assert abc_classes({"a": 70.0, "b": 15.0, "c": 10.0, "d": 5.0}) == {
        "a": "A",
        "b": "A",
        "c": "B",
        "d": "C",
    }
    assert abc_classes({}) == {}
    assert abc_classes({"A": 0.0, "B": 0.0}) == {"A": "C", "B": "C"}


@pytest.mark.parametrize("invalid", [math.inf, -math.inf, math.nan, -1e307])
def test_abc_rejects_non_finite_values(invalid: float) -> None:
    with pytest.raises(ValueError, match="ABC item values must be finite and non-negative"):
        abc_classes({"a": invalid, "b": 1e308, "c": 1e308})


@pytest.mark.parametrize(
    "values",
    [
        {"a": 100.0, "b": -1.0},  # A finite, otherwise-plausible total
        {"a": 1.0, "b": -1.0},  # Previously all C from a zero total
        {"a": 0.0, "b": -0.001},
        {"a": 1e308, "b": 1e308, "c": -0.01},
    ],
)
def test_abc_rejects_negative_item_values_before_scoring(values: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="ABC item values must be finite and non-negative"):
        abc_classes(values)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        (0.0, 0.95),
        (-0.1, 0.95),
        (0.9, 0.9),
        (0.96, 0.95),
        (0.8, 1.01),
        (math.nan, 0.95),
        (0.8, math.nan),
        (math.inf, 0.95),
        (0.8, math.inf),
        (-math.inf, 0.95),
    ],
)
def test_abc_rejects_invalid_cutoffs_even_when_used_directly(a: float, b: float) -> None:
    with pytest.raises(ValueError, match="ABC thresholds must satisfy"):
        abc_classes({"a": 75.0, "b": 25.0}, a=a, b=b)


def test_abc_accepts_valid_upper_boundary_and_zero_values() -> None:
    assert abc_classes({"a": 75.0, "b": 25.0}, a=0.8, b=1.0) == {
        "a": "A",
        "b": "A",
    }
    assert abc_classes({"a": 0.0, "b": 0.0}) == {"a": "C", "b": "C"}


@pytest.mark.parametrize("quantity", ["1e308", "1e307"])
def test_library_rejects_unrepresentable_annual_value_before_policy(quantity: str) -> None:
    rows = [["sku", "period", "quantity", "unit_cost"]]
    rows.extend(["A", str(i), quantity, "2"] for i in range(1, 9))
    data = parse_rows(rows)
    with pytest.raises(DataError, match="sku 'A': annual consumption value exceeds"):
        analyze(data, Config(holdout=2))


def test_cli_rejects_invalid_annual_value_without_replacing_report(tmp_path: Path) -> None:
    path = tmp_path / "oversized.csv"
    rows = ["sku,period,quantity,unit_cost"]
    rows.extend(f"A,{i},1e308,2" for i in range(1, 9))
    write_csv(path, "\n".join(rows) + "\n")
    report = tmp_path / "existing-report.json"
    report.write_text("previous successful report\n", encoding="utf-8")

    result = run_module(
        str(path),
        "--holdout",
        "2",
        "--format",
        "json",
        "--output",
        str(report),
    )
    assert result.returncode == 4
    assert result.stdout == ""
    assert "sku 'A': annual consumption value exceeds" in result.stderr
    assert report.read_text(encoding="utf-8") == "previous successful report\n"
