"""Gzip demand input must preserve uncompressed inventory analysis semantics."""

from __future__ import annotations

import gzip
import json
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import EXAMPLES

from inventory_policy_lab import DataError, InputFileError, read_demand
from inventory_policy_lab.cli import main


def test_gzip_and_plain_readers_agree_with_original_history(tmp_path: Path) -> None:
    original = EXAMPLES / "worked_example.csv"
    packed = tmp_path / "worked_example.CSV.GZ"
    packed.write_bytes(gzip.compress(original.read_bytes()))
    baseline = read_demand(original)
    compressed = read_demand(packed)
    assert replace(compressed, source=baseline.source) == baseline
    assert compressed.source == packed.as_posix()


def test_gzip_utf8_bom_and_quoted_cells_use_standard_parser(tmp_path: Path) -> None:
    original = "\ufeffsku,period,quantity,extra\nA,2026-01,3,\"North, East\"\nA,2026-02,4,South\n"
    plain = tmp_path / "source.csv"
    compressed = tmp_path / "source.csv.gz"
    plain.write_text(original, encoding="utf-8")
    compressed.write_bytes(gzip.compress(original.encode("utf-8")))
    assert replace(read_demand(compressed), source="same") == replace(
        read_demand(plain), source="same"
    )
    assert read_demand(compressed).skus[0].demand == (3.0, 4.0)


def test_gzip_allows_cost_columns_and_json_cli_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = EXAMPLES / "worked_example.csv"
    packed = tmp_path / "history.csv.gz"
    packed.write_bytes(gzip.compress(source.read_bytes()))
    assert main([str(packed), "--format", "json", "--holdout", "2"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["source"] == packed.as_posix()
    assert result["rows"] == 16
    assert result["summary"]["skus"] == 2


def test_gzip_invalid_rows_remain_data_errors(tmp_path: Path) -> None:
    path = tmp_path / "invalid.csv.gz"
    path.write_bytes(gzip.compress(b"sku,period,quantity\nA,1,-3\n"))
    with pytest.raises(DataError, match="negative quantity") as exc:
        read_demand(path)
    assert exc.value.exit_code == 4


@pytest.mark.parametrize("kind", ("not_gzip", "truncated", "bad_crc"))
def test_corrupt_gzip_is_clean_input_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], kind: str
) -> None:
    path = tmp_path / "corrupt.csv.gz"
    valid = gzip.compress(b"sku,period,quantity\nA,1,3\n")
    if kind == "not_gzip":
        payload = b"sku,period,quantity\nA,1,3\n"
    elif kind == "truncated":
        payload = valid[:-8]
    else:
        payload = valid[:-1] + bytes([valid[-1] ^ 255])
    path.write_bytes(payload)
    output = tmp_path / "existing.json"
    output.write_text('{"old_report": true}\n', encoding="utf-8")
    assert main([str(path), "--format", "json", "--output", str(output)]) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "inventory-policy-lab: error:" in captured.err
    assert "Traceback" not in captured.err
    assert output.read_text(encoding="utf-8") == '{"old_report": true}\n'


def test_non_utf8_gzip_is_a_clean_input_error(tmp_path: Path) -> None:
    path = tmp_path / "latin1.csv.gz"
    path.write_bytes(gzip.compress("sku,period,quantity\ncaño,1,2\n".encode("latin-1")))
    with pytest.raises(InputFileError, match="not valid UTF-8") as exc:
        read_demand(path)
    assert exc.value.exit_code == 3


def test_report_and_input_may_not_resolve_to_same_gzip_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_path = tmp_path / "sample.csv.gz"
    original = gzip.compress(b"sku,period,quantity\nA,1,2\n")
    input_path.write_bytes(original)
    assert main([str(input_path), "--format", "json", "--output", str(input_path)]) == 3
    assert "refusing to overwrite input CSV" in capsys.readouterr().err
    assert input_path.read_bytes() == original
