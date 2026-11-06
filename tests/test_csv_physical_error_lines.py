"""CSV input errors identify real source lines, not logical record positions."""

from __future__ import annotations

import gzip
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

from inventory_policy_lab import ConfigError, DataError, parse_rows, read_demand

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("source", "error"),
    [
        (
            'sku,period,quantity,notes\nA,1,2,"North\nbranch"\nB,2,invalid,ok\n',
            "line 4: quantity 'invalid'",
        ),
        (
            'sku,period,quantity,"long\nheading"\nA,1,invalid,ok\n',
            "line 3: quantity 'invalid'",
        ),
        (
            'sku,period,quantity,notes\nA,1,2,"North\nbranch"\nB,2,3\n',
            "line 4: expected 4 fields from header",
        ),
        (
            'sku,period,quantity,notes\nA,1,2,"North\nbranch"\n,2,3,ok\n',
            "line 4: empty sku",
        ),
    ],
)
def test_multiline_fields_keep_physical_source_positions(
    tmp_path: Path, source: str, error: str
) -> None:
    path = tmp_path / "input.csv"
    path.write_bytes(source.encode("utf-8"))
    with pytest.raises(DataError, match=error) as info:
        read_demand(path)
    assert info.value.exit_code == 4


def test_excel_hint_and_crlf_multiline_field_with_gzip(tmp_path: Path) -> None:
    source = 'sep=;\r\nsku;period;quantity;notes\r\nA;1;2;"two\r\nlines"\r\nB;2;bad;ok\r\n'
    path = tmp_path / "demand.csv.gz"
    path.write_bytes(gzip.compress(source.encode("utf-8-sig")))
    with pytest.raises(DataError, match="line 5: quantity 'bad'") as info:
        read_demand(path, delimiter="semicolon")
    assert info.value.exit_code == 4


def test_direct_parser_keeps_existing_record_number_contract() -> None:
    rows = [
        ["sku", "period", "quantity"],
        ["A", "1", "2"],
        ["B", "2", "wrong"],
    ]
    with pytest.raises(DataError, match="line 3: quantity 'wrong'"):
        parse_rows(rows)
    with pytest.raises(DataError, match="line 4: quantity 'wrong'"):
        parse_rows(rows, line_offset=1)



def test_direct_parser_uses_supplied_physical_record_positions() -> None:
    rows = [
        ["sku", "period", "quantity", "notes"],
        ["A", "1", "2", "North\\nbranch"],
        ["B", "2", "invalid", "ok"],
    ]
    with pytest.raises(DataError, match="line 4: quantity 'invalid'"):
        parse_rows(rows, record_lines=[1, 2, 4])
    # An Excel separator preamble shifts physical positions by one line.
    with pytest.raises(DataError, match="line 5: quantity 'invalid'"):
        parse_rows(rows, line_offset=1, record_lines=[2, 3, 5])


@pytest.mark.parametrize(
    "metadata",
    [
        [],
        [1, 2],
        [1, 2, 3, 4],
        [1, 2, 2],
        [1, 3, 2],
        [1, 0, 3],
        [-1, 2, 3],
        [1, True, 3],
        [1, 2.5, 3],
        [1, "2", 3],
        "1,2,3",
        {0: 1, 1: 2, 2: 3},
    ],
)
def test_direct_parser_rejects_invalid_physical_metadata(metadata: object) -> None:
    rows = [
        ["sku", "period", "quantity"],
        ["A", "1", "2"],
        ["B", "2", "invalid"],
    ]
    with pytest.raises(ConfigError, match="record_lines must contain one increasing") as info:
        parse_rows(rows, record_lines=cast(list[int], metadata))
    assert info.value.exit_code == 2


@pytest.mark.parametrize("invalid", [True, False, None, -1, 1.5, "1"])
def test_direct_parser_rejects_invalid_line_offset(invalid: object) -> None:
    rows = [["sku", "period", "quantity"], ["A", "1", "2"]]
    with pytest.raises(ConfigError, match="line_offset must be a non-negative integer") as info:
        parse_rows(rows, line_offset=cast(int, invalid))
    assert info.value.exit_code == 2


def test_direct_parser_accepts_header_only_metadata_then_preserves_data_error() -> None:
    with pytest.raises(DataError, match="header but no data rows"):
        parse_rows([["sku", "period", "quantity"]], record_lines=[1])


def test_cli_preserves_existing_report_after_multiline_error(tmp_path: Path) -> None:
    source = tmp_path / "demand.csv"
    source.write_text(
        'sku,period,quantity,notes\nA,1,2,"North\nbranch"\nB,2,wrong,ok\n',
        encoding="utf-8",
    )
    report = tmp_path / "previous.json"
    report.write_text('{"previous":"verified"}\n', encoding="utf-8")
    proc = subprocess.run(
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
    assert proc.returncode == 4
    assert "line 4: quantity 'wrong'" in proc.stderr
    assert "Traceback" not in proc.stderr
    assert proc.stdout == ""
    assert report.read_text(encoding="utf-8") == '{"previous":"verified"}\n'
