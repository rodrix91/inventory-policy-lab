"""EOQ must stay finite when only an intermediate floating-point product overflows."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from conftest import run_module, write_csv

from inventory_policy_lab import Config, analyze, eoq, parse_rows


@pytest.mark.parametrize(
    ("demand", "ordering", "holding", "expected"),
    [
        (1e200, 1e200, 1e200, math.sqrt(2) * 1e100),
        (1e308, 1e308, 1e308, math.sqrt(2) * 1e154),
        (1e-200, 1e-200, 1e-200, math.sqrt(2) * 1e-100),
        (1e-300, 1e-300, 1e-300, math.sqrt(2) * 1e-150),
    ],
)
def test_eoq_avoids_intermediate_overflow_and_underflow(
    demand: float, ordering: float, holding: float, expected: float
) -> None:
    result = eoq(demand, ordering, holding)
    assert result is not None
    assert math.isfinite(result)
    assert result == pytest.approx(expected, rel=1e-12)


def test_eoq_preserves_ordinary_zero_and_undefined_cases() -> None:
    assert eoq(1200, 30, 0.5) == math.sqrt(2 * 1200 * 30 / 0.5)
    assert eoq(100, 0, 1) == 0
    assert eoq(0, 30, 1) is None
    assert eoq(100, 30, 0) is None


def test_genuinely_unrepresentable_final_quantity_is_not_faked() -> None:
    assert eoq(1e308, 1e308, 1e-308) == math.inf


def test_library_policy_uses_finite_eoq_for_large_valid_costs() -> None:
    rows = [["sku", "period", "quantity", "unit_cost"]]
    rows.extend(["S1", str(i), "1e130", "1"] for i in range(1, 9))
    report = analyze(
        parse_rows(rows),
        Config(holdout=2, ordering_cost=1e180, holding_rate=1e160),
    )
    sku = report.skus[0]
    expected = math.sqrt(2 * 12) * 1e75
    assert sku.policy.eoq == pytest.approx(expected, rel=1e-12)
    assert sku.order_quantity == pytest.approx(expected, rel=1e-12)
    assert sku.order_quantity_source == "eoq"


def test_cli_json_contains_finite_eoq_instead_of_infinity(tmp_path: Path) -> None:
    path = tmp_path / "large-valid-costs.csv"
    rows = ["sku,period,quantity,unit_cost"]
    rows.extend(f"S1,{i},1e130,1" for i in range(1, 9))
    write_csv(path, "\n".join(rows) + "\n")
    result = run_module(
        str(path),
        "--holdout",
        "2",
        "--ordering-cost",
        "1e180",
        "--holding-rate",
        "1e160",
        "--format",
        "json",
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    eoq_units = data["skus"][0]["policy"]["eoq"]
    assert math.isfinite(eoq_units)
    assert eoq_units == pytest.approx(math.sqrt(24) * 1e75, rel=1e-12)
    assert data["skus"][0]["policy"]["order_quantity_source"] == "eoq"
