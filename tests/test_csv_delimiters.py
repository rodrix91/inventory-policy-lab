"""Explicit CSV separators for regional Excel and ERP demand exports."""

from __future__ import annotations

import csv
import gzip
import io
import json
from dataclasses import replace
from pathlib import Path

import pytest

from inventory_policy_lab import ConfigError, DataError, analyze_file, read_demand
from inventory_policy_lab.cli import main

SEPARATORS = {"comma": ",", "semicolon": ";", "tab": "\t", "pipe": "|"}


def _export(separator: str) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter=separator, lineterminator="\r\n")
    writer.writerow(("sku", "period", "quantity", "unit_cost", "unused"))
    for month in range(1, 9):
        writer.writerow(('Caña; Norte | "A"', f"2026-{month:02d}", str(month), "4.5", "x,y;z|"))
    return stream.getvalue()


@pytest.mark.parametrize("name", tuple(SEPARATORS))
@pytest.mark.parametrize("compressed", (False, True))
def test_reader_configured_separator_matches_comma_with_quotes_and_gzip(
    tmp_path: Path, name: str, compressed: bool
) -> None:
    text = _export(SEPARATORS[name])
    canonical = tmp_path / "canonical.csv"
    canonical.write_text(_export(","), encoding="utf-8-sig")
    source = tmp_path / ("demand.csv.gz" if compressed else "demand.csv")
    content = text.encode("utf-8-sig")
    source.write_bytes(gzip.compress(content) if compressed else content)
    expected = read_demand(canonical)
    actual = read_demand(source, delimiter=name)
    assert replace(actual, source=expected.source) == expected
    assert actual.rows == 8
    assert actual.skus[0].sku == 'Caña; Norte | "A"'
    assert actual.skus[0].unit_cost == 4.5
    assert actual.skus[0].demand == tuple(float(i) for i in range(1, 9))


@pytest.mark.parametrize("name", ("semicolon", "tab", "pipe"))
def test_cli_and_analysis_use_configured_separator(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    path = tmp_path / "regional.csv"
    path.write_text(_export(SEPARATORS[name]), encoding="utf-8")
    result = analyze_file(path, delimiter=name)
    assert result.data.rows == 8
    assert result.data.skus[0].sku == 'Caña; Norte | "A"'
    assert main([str(path), "--delimiter", name, "--format", "json"]) == 0
    output = capsys.readouterr()
    assert output.err == ""
    report = json.loads(output.out)
    assert report["rows"] == 8
    assert report["summary"]["skus"] == 1


def test_cp1252_semicolon_gzip_preserves_encoding_and_cost_fields(tmp_path: Path) -> None:
    path = tmp_path / "regional.csv.gz"
    path.write_bytes(gzip.compress(_export(";").encode("cp1252")))
    history = read_demand(path, delimiter="semicolon", encoding="cp1252")
    assert history.skus[0].sku == 'Caña; Norte | "A"'
    assert history.skus[0].unit_cost == 4.5


@pytest.mark.parametrize("invalid", ("auto", ";", "colon", ""))
def test_unknown_library_separator_is_config_error(tmp_path: Path, invalid: str) -> None:
    path = tmp_path / "valid.csv"
    path.write_text(_export(","), encoding="utf-8")
    with pytest.raises(ConfigError, match="unknown CSV delimiter") as exc:
        read_demand(path, delimiter=invalid)
    assert exc.value.exit_code == 2


def test_unknown_cli_delimiter_is_usage_error_and_does_not_touch_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "valid.csv"
    path.write_text(_export(","), encoding="utf-8")
    report = tmp_path / "old.json"
    report.write_text('{"prior": true}\n', encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main([str(path), "--delimiter", "auto", "--output", str(report)])
    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
    assert report.read_text(encoding="utf-8") == '{"prior": true}\n'


def test_default_comma_does_not_silently_guess_semicolon(tmp_path: Path) -> None:
    source = tmp_path / "regional.csv"
    source.write_text(_export(";"), encoding="utf-8")
    with pytest.raises(DataError, match="malformed CSV quoting|missing required column"):
        read_demand(source)


def test_semicolon_malformed_rows_fail_without_replacing_previous_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "bad.csv"
    source.write_text("sku;period;quantity\nA;2026-01;3;extra\n", encoding="utf-8")
    with pytest.raises(DataError, match="expected 3 fields"):
        read_demand(source, delimiter="semicolon")
    saved = tmp_path / "existing.json"
    saved.write_text('{"previous": true}\n', encoding="utf-8")
    code = main([str(source), "--delimiter", "semicolon", "--format", "json", "-o", str(saved)])
    assert code == 4
    assert "expected 3 fields" in capsys.readouterr().err
    assert saved.read_text(encoding="utf-8") == '{"previous": true}\n'
