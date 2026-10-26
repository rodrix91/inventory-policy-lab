"""Unicode decimal month labels must align with the canonical demand calendar."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from inventory_policy_lab import parse_rows, read_demand
from inventory_policy_lab.cli import main


@pytest.mark.parametrize(
    "month",
    ["٢٠٢٦-٠١", "२०२६-०१", "۲۰۲۶-۰۱", "2026-01"],
)
def test_each_accepted_month_digit_script_keeps_observed_demand(month: str) -> None:
    data = parse_rows(
        [
            ["sku", "period", "quantity"],
            ["A", month, "7"],
        ]
    )
    assert data.period_kind == "month"
    assert data.calendar == ("2026-01",)
    assert data.rows == 1
    assert data.skus[0].periods == ("2026-01",)
    assert data.skus[0].demand == (7.0,)
    assert data.skus[0].filled_periods == 0


def test_mixed_month_digits_aggregate_and_fill_only_genuine_gaps() -> None:
    data = parse_rows(
        [
            ["sku", "period", "quantity"],
            ["A", "٢٠٢٦-٠١", "5"],
            ["A", "2026-01", "2"],
            ["A", "२०२६-०३", "7"],
            ["B", "۲۰۲۶-۰۲", "9"],
        ]
    )
    assert data.calendar == ("2026-01", "2026-02", "2026-03")
    assert data.rows == 4
    a, b = data.skus
    assert a.sku == "A"
    assert a.periods == data.calendar
    assert a.demand == (7.0, 0.0, 7.0)
    assert a.filled_periods == 1
    assert b.sku == "B"
    assert b.periods == ("2026-02", "2026-03")
    assert b.demand == (9.0, 0.0)
    assert b.filled_periods == 1


def test_file_reader_normalizes_months_without_changing_sku_or_amount(
    tmp_path: Path,
) -> None:
    path = tmp_path / "monthly.csv"
    path.write_text(
        "sku,period,quantity\n"
        "item-α,٢٠٢٦-٠١,3\n"
        "item-α,2026-01,4\n"
        "item-α,२०२६-०२,8\n",
        encoding="utf-8",
    )
    data = read_demand(path)
    assert data.period_kind == "month"
    assert data.calendar == ("2026-01", "2026-02")
    assert data.skus[0].sku == "item-α"
    assert data.skus[0].demand == (7.0, 8.0)
    assert data.skus[0].filled_periods == 0


def test_cli_json_reports_original_nonzero_demand_for_unicode_months(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "unicode-months.csv"
    source.write_text(
        "sku,period,quantity\n"
        "A,٢٠٢٦-٠١,3\n"
        "A,2026-01,2\n"
        "A,२०२६-०२,4\n"
        "A,۲۰۲۶-۰۳,5\n"
        "A,2026-04,6\n",
        encoding="utf-8",
    )
    target = tmp_path / "report.json"
    assert main(
        [str(source), "--holdout", "1", "--format", "json", "--output", str(target)]
    ) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    report = json.loads(target.read_text(encoding="utf-8"))
    assert len(report["skus"]) == 1
    assert report["skus"][0]["sku"] == "A"
    assert report["skus"][0]["total_demand"] == 20.0
    assert report["skus"][0]["filled_periods"] == 0
