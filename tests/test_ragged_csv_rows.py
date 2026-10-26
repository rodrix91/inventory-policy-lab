"""Reject CSV row-width drift even when affected columns are not model inputs."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from inventory_policy_lab import DataError, parse_rows, read_demand

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("header", "row", "message"),
    [
        (
            ["sku", "period", "quantity"],
            ["A", "1", "4", "unexpected"],
            "line 2: expected 3 fields from header, found 4",
        ),
        (
            ["sku", "period", "quantity", "comment"],
            ["A", "1", "4"],
            "line 2: expected 4 fields from header, found 3",
        ),
        (
            ["sku", "period", "quantity", "order_cost"],
            ["A", "1", "4"],
            "line 2: expected 4 fields from header, found 3",
        ),
        (
            ["sku", "period", "quantity", "extra", "other"],
            ["A", "1", "4", "note"],
            "line 2: expected 5 fields from header, found 4",
        ),
    ],
)
@pytest.mark.parametrize("cost_columns", [False, True])
def test_every_nonblank_row_must_match_header_width(
    header: list[str], row: list[str], message: str, cost_columns: bool
) -> None:
    # When cost parsing is enabled, order_cost becomes a consumed field.
    # Keep the existing "expected at least" wording for required-field gaps.
    expected = (
        "line 2: expected at least 4 fields, found 3"
        if cost_columns and header[-1] == "order_cost"
        else message
    )
    with pytest.raises(DataError, match=expected) as info:
        parse_rows([header, row], cost_columns=cost_columns)
    assert info.value.exit_code == 4


def test_missing_required_fields_keep_their_original_actionable_message() -> None:
    with pytest.raises(DataError, match="line 2: expected at least 3 fields, found 2"):
        parse_rows([["sku", "period", "quantity"], ["A", "1"]])


def test_valid_extra_columns_and_explicit_empty_cells_remain_accepted() -> None:
    data = parse_rows(
        [
            ["sku", "period", "quantity", "notes", "optional"],
            ["A", "1", "4", "North, region", ""],
            ["A", "2", "3", "", "n/a"],
            ["", "", "", "", ""],
        ]
    )
    assert data.rows == 2
    assert data.skus[0].demand == (4.0, 3.0)


def test_quoted_commas_and_multiline_fields_remain_valid(tmp_path: Path) -> None:
    source = tmp_path / "valid.csv"
    source.write_text(
        'sku,period,quantity,note\nA,1,4,"city, branch"\n'
        'A,2,3,"multiple\nlines"\n',
        encoding="utf-8",
    )
    parsed = read_demand(source)
    assert parsed.rows == 2
    assert parsed.skus[0].demand == (4.0, 3.0)


@pytest.mark.parametrize(
    "content",
    [
        "sku,period,quantity\nA,1,4,extra\n",
        "sku,period,quantity,notes\nA,1,4\n",
    ],
)
def test_cli_fails_closed_and_preserves_existing_json_report(
    tmp_path: Path, content: str
) -> None:
    source = tmp_path / "bad.csv"
    source.write_text(content, encoding="utf-8")
    report = tmp_path / "verified.json"
    report.write_text('{"verified":true}\n', encoding="utf-8")
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "inventory_policy_lab",
            str(source),
            "--format",
            "json",
            "--output",
            str(report),
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 4, process.stderr
    assert "line 2: expected" in process.stderr
    assert "fields from header" in process.stderr
    assert not process.stdout
    assert "Traceback" not in process.stderr
    assert report.read_text(encoding="utf-8") == '{"verified":true}\n'
