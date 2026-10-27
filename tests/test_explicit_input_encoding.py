"""Explicit text decoding for CSV and gzip demand exports, with safe failures."""

from __future__ import annotations

import gzip
import json
from dataclasses import replace
from pathlib import Path

import pytest

from inventory_policy_lab import ConfigError, InputFileError, analyze_file, read_demand
from inventory_policy_lab.cli import main


def _history_text() -> str:
    return (
        "sku,period,quantity,unit_cost\n"
        "Caña,2026-01,3,4.50\n"
        "Caña,2026-02,2,4.50\n"
        "Caña,2026-03,4,4.50\n"
        "Caña,2026-04,5,4.50\n"
        "Caña,2026-05,3,4.50\n"
        "Caña,2026-06,4,4.50\n"
        "Caña,2026-07,3,4.50\n"
        "Caña,2026-08,2,4.50\n"
    )


def test_cp1252_plain_and_gzip_match_utf8_and_preserve_accents(tmp_path: Path) -> None:
    source = _history_text()
    utf8 = tmp_path / "input-utf8.csv"
    cp1252 = tmp_path / "input-cp1252.csv"
    compressed = tmp_path / "input-cp1252.csv.gz"
    utf8.write_text(source, encoding="utf-8")
    cp1252.write_bytes(source.encode("cp1252"))
    compressed.write_bytes(gzip.compress(source.encode("cp1252")))
    expected = read_demand(utf8)
    for path in (cp1252, compressed):
        decoded = read_demand(path, encoding="cp1252")
        assert replace(decoded, source=expected.source) == expected
        assert decoded.skus[0].sku == "Caña"
        assert decoded.skus[0].unit_cost == 4.5
    assert analyze_file(cp1252, encoding="cp1252").data.skus[0].sku == "Caña"


def test_cli_cp1252_gzip_json_and_output_are_compatible(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    packed = tmp_path / "demand.csv.gz"
    packed.write_bytes(gzip.compress(_history_text().encode("cp1252")))
    output = tmp_path / "report.json"
    assert main([str(packed), "--encoding", "cp1252", "--format", "json", "-o", str(output)]) == 0
    assert capsys.readouterr().err == ""
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["summary"]["skus"] == 1
    assert report["skus"][0]["sku"] == "Caña"
    assert report["rows"] == 8


def test_utf16_bom_plain_and_gzip_match_utf8(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _history_text()
    utf8 = tmp_path / "baseline.csv"
    utf8.write_text(source, encoding="utf-8")
    expected = read_demand(utf8)
    for gzip_input in (False, True):
        with pytest.raises(InputFileError, match="not valid UTF-8"):
            path = tmp_path / ("utf16.csv.gz" if gzip_input else "utf16.csv")
            content = source.encode("utf-16")
            path.write_bytes(gzip.compress(content) if gzip_input else content)
            read_demand(path)
        decoded = read_demand(path, encoding="utf-16")
        assert replace(decoded, source=expected.source) == expected
        assert main([str(path), "--encoding", "utf-16", "--format", "json"]) == 0
        assert json.loads(capsys.readouterr().out)["rows"] == 8


def test_explicit_utf8_alias_preserves_bom_and_default_header(
    tmp_path: Path,
) -> None:
    path = tmp_path / "bom.csv"
    path.write_bytes(("\ufeff" + _history_text()).encode("utf-8"))
    expected = read_demand(path)
    assert read_demand(path, encoding="utf-8") == expected
    assert read_demand(path, encoding="UTF_8") == expected


@pytest.mark.parametrize(
    ("codec", "message"),
    [
        ("unknown-erp-encoding", "unknown input encoding"),
        ("base64_codec", "is not a text codec"),
    ],
)
def test_invalid_codec_is_usage_error_without_overwriting_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    codec: str,
    message: str,
) -> None:
    source = tmp_path / "orders.csv"
    source.write_text(_history_text(), encoding="utf-8")
    report = tmp_path / "existing.json"
    report.write_text('{"preserve": true}\n', encoding="utf-8")
    with pytest.raises(ConfigError, match=message) as info:
        read_demand(source, encoding=codec)
    assert info.value.exit_code == 2
    assert main([str(source), "--encoding", codec, "-o", str(report)]) == 2
    captured = capsys.readouterr()
    assert message in captured.err
    assert "Traceback" not in captured.err
    assert report.read_text(encoding="utf-8") == '{"preserve": true}\n'


def test_incorrect_selected_codec_returns_input_error_and_keeps_prior_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "legacy.csv"
    source.write_bytes(_history_text().encode("cp1252"))
    report = tmp_path / "previous.json"
    report.write_text('{"verified": true}\n', encoding="utf-8")
    assert main([str(source), "--format", "json", "-o", str(report)]) == 3
    captured = capsys.readouterr()
    assert "not valid UTF-8" in captured.err
    assert not captured.out
    assert report.read_text(encoding="utf-8") == '{"verified": true}\n'
    # Incompatible UTF-16 mode must fail explicitly instead of guessing.
    with pytest.raises(InputFileError, match="not valid utf-16"):
        read_demand(source, encoding="utf-16")


def test_non_utf8_custom_codec_rejects_invalid_bytes_cleanly(tmp_path: Path) -> None:
    path = tmp_path / "ascii.csv.gz"
    path.write_bytes(gzip.compress(_history_text().encode("utf-8")))
    with pytest.raises(InputFileError, match="not valid ascii") as exc:
        read_demand(path, encoding="ascii")
    assert exc.value.exit_code == 3
