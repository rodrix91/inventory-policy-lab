"""Monthly demand labels must use real calendar years (0001 through 9999)."""

from __future__ import annotations

from pathlib import Path

import pytest

from inventory_policy_lab import DataError, parse_rows
from inventory_policy_lab.cli import main


@pytest.mark.parametrize("month", ["0000-01", "0000-12", "٠٠٠٠-٠١", "००००-०१"])
def test_year_zero_month_is_rejected_with_source_row(month: str) -> None:
    with pytest.raises(DataError, match=r"line 2: period .* is not YYYY-MM") as info:
        parse_rows([["sku", "period", "quantity"], ["A", month, "5"]])
    assert info.value.exit_code == 4


@pytest.mark.parametrize(
    ("month", "canonical"),
    [
        ("0001-01", "0001-01"),
        ("9999-12", "9999-12"),
        ("٠٠٠١-٠١", "0001-01"),
    ],
)
def test_valid_month_year_boundaries_keep_demand(month: str, canonical: str) -> None:
    data = parse_rows([["sku", "period", "quantity"], ["A", month, "5"]])
    assert data.calendar == (canonical,)
    assert data.skus[0].demand == (5.0,)
    assert data.skus[0].filled_periods == 0


def test_invalid_year_zero_in_file_preserves_existing_json_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "bad-year.csv"
    source.write_text(
        "sku,period,quantity\nA,2026-01,5\nA,0000-02,7\n", encoding="utf-8"
    )
    target = tmp_path / "verified-report.json"
    previous = '{"report":"previously verified"}\n'
    target.write_text(previous, encoding="utf-8")

    assert main([str(source), "--format", "json", "--output", str(target)]) == 4
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "line 3: period '0000-02'" in captured.err
    assert "Traceback" not in captured.err
    assert target.read_text(encoding="utf-8") == previous
