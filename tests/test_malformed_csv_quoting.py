"""Strict parsing protects inventory forecasts from corrupted quoted CSV values."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from inventory_policy_lab import DataError, read_demand

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ('sku,period,quantity\nA,1,"12"extra\n', "expected after"),
        ('sku,period,quantity\n"A\n', "unexpected end of data"),
    ],
)
def test_malformed_quotes_raise_data_error(
    tmp_path: Path, source: str, message: str
) -> None:
    path = tmp_path / "malformed.csv"
    path.write_text(source, encoding="utf-8")
    with pytest.raises(DataError, match="malformed CSV quoting near line") as info:
        read_demand(path)
    assert info.value.exit_code == 4
    assert message in str(info.value)
    assert str(path) in str(info.value)


def test_quoted_commas_and_multiline_sku_are_valid(tmp_path: Path) -> None:
    path = tmp_path / "valid.csv"
    path.write_text('sku,period,quantity\n"North, A",1,12\n"South\nB",1,5\n', encoding="utf-8")
    data = read_demand(path)
    assert data.rows == 2
    assert [(history.sku, history.demand) for history in data.skus] == [
        ("North, A", (12.0,)),
        ("South\nB", (5.0,)),
    ]


def test_cli_preserves_existing_report_after_quote_error(tmp_path: Path) -> None:
    path = tmp_path / "invalid.csv"
    path.write_text('sku,period,quantity\n"A"extra,1,12\n', encoding="utf-8")
    output = tmp_path / "report.json"
    output.write_text("verified prior report\n", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "inventory_policy_lab",
            str(path),
            "--format",
            "json",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 4
    assert "malformed CSV quoting near line" in proc.stderr
    assert not proc.stdout
    assert output.read_text(encoding="utf-8") == "verified prior report\n"
