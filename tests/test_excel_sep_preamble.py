"""Excel sep= preambles are metadata, not demand history columns."""

from __future__ import annotations

import gzip
import json
from dataclasses import replace
from pathlib import Path

import pytest

from inventory_policy_lab import DataError, read_demand
from inventory_policy_lab.cli import main


def _sample(separator: str, sku: str = "Caña") -> str:
    header = separator.join(("sku", "period", "quantity"))
    values = [
        separator.join((sku, str(period), str(period + 1)))
        for period in range(1, 9)
    ]
    return "\n".join((header, *values)) + "\n"


@pytest.mark.parametrize(
    ("separator", "choice"),
    [(",", "comma"), (";", "semicolon"), ("\t", "tab"), ("|", "pipe")],
)
def test_excel_hint_matches_equivalent_plain_input(
    tmp_path: Path, separator: str, choice: str
) -> None:
    plain = tmp_path / "plain.csv"
    excel = tmp_path / "excel.csv"
    plain.write_text(_sample(separator), encoding="utf-8")
    # Write exact CRLF bytes; Path.write_text would turn \n into \r\n again on Windows.
    excel.write_bytes((f"SEP={separator}\r\n" + _sample(separator)).encode("utf-8"))
    expected = read_demand(plain, delimiter=choice)
    parsed = read_demand(excel, delimiter=choice)
    assert replace(parsed, source=expected.source) == expected
    assert parsed.rows == 8
    assert parsed.skus[0].sku == "Caña"


@pytest.mark.parametrize("codec", ("cp1252", "utf-16"))
def test_excel_hint_gzip_with_explicit_encoding(
    tmp_path: Path, codec: str
) -> None:
    original = _sample(";")
    plain = tmp_path / "plain.csv"
    packed = tmp_path / "excel.csv.gz"
    plain.write_bytes(original.encode(codec))
    packed.write_bytes(gzip.compress(("sep=;\n" + original).encode(codec)))
    expected = read_demand(plain, delimiter="semicolon", encoding=codec)
    parsed = read_demand(packed, delimiter="semicolon", encoding=codec)
    assert replace(parsed, source=expected.source) == expected


def test_utf8_bom_before_excel_hint_is_removed(tmp_path: Path) -> None:
    path = tmp_path / "excel.csv"
    path.write_text("\ufeffsep=;\n" + _sample(";"), encoding="utf-8")
    assert read_demand(path, delimiter="semicolon").rows == 8


def test_cli_excel_hint_outputs_report_without_changing_existing_rules(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    excel = tmp_path / "erp.csv"
    output = tmp_path / "report.json"
    excel.write_text("sep=;\n" + _sample(";"), encoding="utf-8")
    assert (
        main([str(excel), "--delimiter", "semicolon", "--format", "json", "-o", str(output)])
        == 0
    )
    assert capsys.readouterr().err == ""
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["rows"] == 8
    assert report["summary"]["skus"] == 1


@pytest.mark.parametrize(
    ("preamble", "choice", "message"),
    [
        ("sep=;", "comma", "pass --delimiter semicolon instead of comma"),
        ("sep=,", "semicolon", "pass --delimiter comma instead of semicolon"),
        ("sep=:", "comma", "unsupported Excel separator"),
    ],
)
def test_conflicting_or_unknown_preamble_is_data_error_and_keeps_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    preamble: str,
    choice: str,
    message: str,
) -> None:
    excel = tmp_path / "bad.csv"
    output = tmp_path / "previous.json"
    excel.write_text(preamble + "\n" + _sample(";"), encoding="utf-8")
    output.write_text('{"keep": true}\n', encoding="utf-8")
    with pytest.raises(DataError, match=message) as info:
        read_demand(excel, delimiter=choice)
    assert info.value.exit_code == 4
    assert main([
        str(excel), "--delimiter", choice, "--format", "json", "-o", str(output)
    ]) == 4
    captured = capsys.readouterr()
    assert message in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""
    assert output.read_text(encoding="utf-8") == '{"keep": true}\n'


def test_data_error_line_counts_excel_preamble(tmp_path: Path) -> None:
    excel = tmp_path / "bad-quantity.csv"
    excel.write_text(
        "sep=;\nsku;period;quantity\nA;1;invalid\n", encoding="utf-8"
    )
    with pytest.raises(DataError, match="line 3: quantity") as info:
        read_demand(excel, delimiter="semicolon")
    assert info.value.exit_code == 4


def test_malformed_quoting_line_counts_excel_preamble(tmp_path: Path) -> None:
    excel = tmp_path / "unclosed-quote.csv"
    excel.write_text(
        'sep=;\nsku;period;quantity\n"A;1;3\n', encoding="utf-8"
    )
    with pytest.raises(DataError, match="malformed CSV quoting near line 3"):
        read_demand(excel, delimiter="semicolon")


def test_normal_multiline_quoted_header_is_not_changed(tmp_path: Path) -> None:
    source = 'sku,period,quantity,"multi\nline"\nA,1,2,ignored\n'
    path = tmp_path / "multiline.csv"
    path.write_text(source, encoding="utf-8")
    assert read_demand(path).skus[0].demand == (2.0,)


def test_longer_sep_prefix_is_not_accepted_as_a_hint(tmp_path: Path) -> None:
    path = tmp_path / "ordinary.csv"
    path.write_text("sep=quantity,period,quantity\nA,1,3\n", encoding="utf-8")
    with pytest.raises(DataError, match="missing required column"):
        read_demand(path)
