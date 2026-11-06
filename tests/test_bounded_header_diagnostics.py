"""Regression coverage for bounded, single-line untrusted CSV header errors."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from inventory_policy_lab import DataError, parse_rows
from inventory_policy_lab.cli import main


def test_short_missing_header_diagnostic_keeps_existing_wording() -> None:
    with pytest.raises(DataError) as caught:
        parse_rows([["sku", "qty"], ["A", "1"]])
    assert str(caught.value) == ("missing required column(s): period/date (header: sku, qty)")


def test_missing_required_header_with_controls_and_large_names_is_bounded() -> None:
    bad = "supplier\n::error::forged\r\x1b[31m\u202e" + "x" * 8000 + "PRIVATE-TAIL"
    with pytest.raises(DataError, match="missing required column") as caught:
        parse_rows([[bad, "extra"], ["A", "1"]])
    message = str(caught.value)
    assert "[truncated]" in message
    assert len(message) < 350
    assert "PRIVATE-TAIL" not in message
    assert "x" * 150 not in message
    assert "\n" not in message
    assert "\r" not in message
    assert "\x1b" not in message
    assert "\u202e" not in message
    assert r"\n" in message
    assert r"\x1b" in message


def test_many_unknown_header_names_report_bounded_inventory() -> None:
    header = [f"extra{index}" for index in range(15)]
    with pytest.raises(DataError) as caught:
        parse_rows([header, ["value"] * len(header)])
    message = str(caught.value)
    assert message.endswith("(header: extra0, extra1, extra2 (+12 more))")
    assert "extra14" not in message
    assert header[-1] == "extra14"


def test_short_ambiguous_header_diagnostic_keeps_source_columns() -> None:
    with pytest.raises(DataError) as caught:
        parse_rows([["sku", "SKU ", "period", "quantity"], ["A", "B", "1", "2"]])
    assert str(caught.value) == (
        "ambiguous sku columns: 'sku' (column 1), 'SKU ' (column 2); keep only one"
    )


def test_many_ambiguous_aliases_are_bounded_and_escape_newline() -> None:
    header = ["sku", "sku\n", "SKU\t", " sku ", "SKU", "period", "quantity"]
    with pytest.raises(DataError, match="ambiguous sku columns") as caught:
        parse_rows([header, ["A", "B", "C", "D", "E", "1", "2"]])
    message = str(caught.value)
    assert "'sku' (column 1)" in message
    assert r"'sku\n' (column 2)" in message
    assert r"'SKU\t' (column 3)" in message
    assert "(+2 more)" in message
    assert "(column 5)" not in message
    assert "\n" not in message
    assert "\t" not in message
    assert len(message) < 220


def test_cli_rejects_long_multiline_header_without_clobbering_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = "private\n::warning::forged\x1b\u202e" + "Y" * 8000 + "PRIVATE-END"
    source = tmp_path / "untrusted.csv"
    with source.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([bad, "unused"])
        writer.writerow(["A", "1"])
    output = tmp_path / "existing.json"
    original = '{"previous":"verified"}\n'
    output.write_text(original, encoding="utf-8")

    status = main([str(source), "--format", "json", "--output", str(output)])
    captured = capsys.readouterr()

    assert status == 4
    assert captured.out == ""
    assert captured.err.count("\n") == 1
    assert "[truncated]" in captured.err
    assert "PRIVATE-END" not in captured.err
    assert "\x1b" not in captured.err
    assert "\u202e" not in captured.err
    assert len(captured.err) < 450
    assert output.read_text(encoding="utf-8") == original
