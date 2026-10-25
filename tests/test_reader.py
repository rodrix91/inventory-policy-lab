"""Reading demand history: columns, periods, calendars, and errors."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from conftest import EXAMPLES, write_csv

from inventory_policy_lab import DataError, InputFileError, parse_rows, read_demand


def rows(text: str) -> list[list[str]]:
    return [line.split(",") for line in text.strip().splitlines()]


def test_reads_the_worked_example() -> None:
    data = read_demand(EXAMPLES / "worked_example.csv")
    assert data.rows == 16
    assert data.period_kind == "integer"
    assert data.calendar == tuple(str(i) for i in range(1, 9))
    assert data.has_unit_cost and data.has_lead_time
    w1, w2 = data.skus
    assert w1.sku == "W-1"
    assert w1.demand == (10, 12, 8, 10, 14, 6, 10, 14)
    assert w1.unit_cost == 2.0
    assert w1.lead_times == (2.0,)
    assert w1.lead_time_periods == ("1",)  # each lead time is dated by its row
    assert w2.lead_times == () and w2.lead_time_periods == ()
    assert w1.filled_periods == 0


def test_accepts_str_paths_and_header_aliases(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "d.csv", "\ufeff SKU ,Date,Qty\nx,2026-01-05,3\nx,2026-01-12,4\n")
    data = read_demand(str(path))
    assert data.period_kind == "date"
    assert data.skus[0].demand == (3, 4)
    assert not data.has_unit_cost and not data.has_lead_time
    assert data.skus[0].unit_cost is None
    assert data.source == path.as_posix()


def test_months_fill_gaps_and_new_items_start_late() -> None:
    data = parse_rows(
        rows(
            """sku,period,demand
a,2025-11,5
a,2026-02,7
b,2026-01,2
b,2026-01,3
"""
        )
    )
    assert data.calendar == ("2025-11", "2025-12", "2026-01", "2026-02")
    a, b = data.skus
    assert a.demand == (5, 0, 0, 7) and a.filled_periods == 2
    # b starts at its first month; two rows of the same month are summed
    assert b.periods == ("2026-01", "2026-02") and b.demand == (5, 0)


def test_integer_calendar_is_complete() -> None:
    data = parse_rows(rows("sku,period,quantity\na,3,1\na,1,2\n"))
    assert data.calendar == ("1", "2", "3")
    assert data.skus[0].demand == (2, 0, 1)


def test_blank_lines_are_skipped_and_cost_and_lead_time_use_non_empty_values() -> None:
    data = parse_rows(
        [
            ["sku", "period", "quantity", "unit_cost", "lead_time"],
            ["a", "1", "1", "2.5", ""],
            ["", "", "", "", ""],
            ["a", "2", "1", "", "3"],
            ["a", "3", "1", "3.0", "1"],
        ]
    )
    assert data.rows == 3
    assert data.skus[0].unit_cost == 3.0  # the most recent non-empty value
    assert data.skus[0].lead_times == (3.0, 1.0)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("sku,quantity\na,1\n", "missing required column(s): period/date"),
        ("sku,period,quantity\na,1\n", "line 2: expected at least 3 fields"),
        ("sku,period,quantity\n,1,1\n", "line 2: empty sku"),
        ("sku,period,quantity\na,2026-13,1\n", "is not YYYY-MM, YYYY-MM-DD or an integer"),
        ("sku,period,quantity\na,2026-02-30,1\n", "is not YYYY-MM, YYYY-MM-DD or an integer"),
        ("sku,period,quantity\na,Q1,1\n", "is not YYYY-MM"),
        ("sku,period,quantity\na,1,1\na,2026-01,1\n", "mixes period formats (integer and month)"),
        ("sku,period,quantity\na,1,\n", "line 2: empty quantity for sku 'a'"),
        ("sku,period,quantity\na,1,ten\n", "line 2: quantity 'ten' is not a number"),
        ("sku,period,quantity\na,1,nan\n", "is not a finite number"),
        ("sku,period,quantity\na,1,-2\n", "negative quantity -2"),
        ("sku,period,quantity,unit_cost\na,1,2,-1\n", "negative unit_cost -1"),
        ("sku,period,quantity,lead_time\na,1,2,-1\n", "negative lead_time -1"),
        ("sku,period,quantity\n\n", "has a header but no data rows"),
    ],
)
def test_invalid_data_is_a_data_error(text: str, message: str) -> None:
    with pytest.raises(DataError) as excinfo:
        parse_rows(rows(text) if text.strip() else [["sku", "period", "quantity"]])
    assert message in str(excinfo.value)
    assert excinfo.value.exit_code == 4


def test_empty_file_is_a_data_error(tmp_path: Path) -> None:
    with pytest.raises(DataError, match="is empty"):
        read_demand(write_csv(tmp_path / "empty.csv", ""))


def test_missing_file_directory_and_encoding_are_input_errors(tmp_path: Path) -> None:
    with pytest.raises(InputFileError, match="file not found"):
        read_demand(tmp_path / "nope.csv")
    with pytest.raises(InputFileError, match="not a file"):
        read_demand(tmp_path)
    latin1 = tmp_path / "latin1.csv"
    latin1.write_bytes("sku,period,quantity\nca\xf1o,1,1\n".encode("latin-1"))
    with pytest.raises(InputFileError, match="not valid UTF-8") as excinfo:
        read_demand(latin1)
    assert excinfo.value.exit_code == 3


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (FileNotFoundError(), "file not found"),
        (IsADirectoryError(), "not a file"),
    ],
)
def test_open_race_errors_are_input_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: OSError, message: str
) -> None:
    path = write_csv(tmp_path / "race.csv", "sku,period,quantity\na,1,1\n")

    def fail_open(self: Path, *args: object, **kwargs: object) -> object:
        raise error

    monkeypatch.setattr(Path, "open", fail_open)
    with pytest.raises(InputFileError, match=message):
        read_demand(path)


@pytest.mark.parametrize(
    ("error", "explanation"),
    [
        (PermissionError("access denied"), "access denied"),
        (OSError("device read error"), "device read error"),
    ],
)
def test_unreadable_csv_errors_are_input_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: OSError, explanation: str
) -> None:
    source = write_csv(tmp_path / "blocked.csv", "sku,period,quantity\na,1,5\n")

    def fail_open(self: Path, *args: object, **kwargs: object) -> object:
        raise error

    monkeypatch.setattr(Path, "open", fail_open)
    with pytest.raises(InputFileError, match="cannot read") as info:
        read_demand(source)
    assert info.value.exit_code == 3
    assert str(source) in str(info.value)
    assert explanation in str(info.value)


def test_cli_read_failure_preserves_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from inventory_policy_lab.cli import main

    source = write_csv(tmp_path / "blocked.csv", "sku,period,quantity\na,1,5\n")
    output = tmp_path / "existing.json"
    output.write_text("verified report\n", encoding="utf-8")
    real_open = Path.open

    def deny_input(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self == source:
            raise PermissionError("permission denied by test")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny_input)
    assert main([str(source), "--format", "json", "--output", str(output)]) == 3
    captured = capsys.readouterr()
    assert not captured.out
    assert "cannot read" in captured.err
    assert "permission denied by test" in captured.err
    assert "Traceback" not in captured.err
    assert output.read_text(encoding="utf-8") == "verified report\n"


@pytest.mark.parametrize(
    ("probe", "error"),
    [
        ("exists", PermissionError("metadata access denied")),
        ("is_file", OSError("filesystem metadata error")),
    ],
)
def test_metadata_probe_errors_are_clean_input_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, probe: str, error: OSError
) -> None:
    source = write_csv(tmp_path / "restricted.csv", "sku,period,quantity\na,1,4\n")

    def fail_metadata(self: Path) -> bool:
        raise error

    monkeypatch.setattr(Path, probe, fail_metadata)
    with pytest.raises(InputFileError, match="cannot read") as info:
        read_demand(source)
    assert info.value.exit_code == 3
    assert str(source) in str(info.value)
    assert str(error) in str(info.value)


def test_cli_metadata_failure_keeps_existing_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from inventory_policy_lab.cli import main

    source = write_csv(tmp_path / "restricted.csv", "sku,period,quantity\na,1,4\n")
    output = tmp_path / "existing.json"
    output.write_text("previous valid report\n", encoding="utf-8")
    real_is_file = Path.is_file

    def fail_input_metadata(self: Path) -> bool:
        if self == source:
            raise PermissionError("restricted input metadata")
        return real_is_file(self)

    monkeypatch.setattr(Path, "is_file", fail_input_metadata)
    assert main([str(source), "--format", "json", "--output", str(output)]) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "cannot read" in captured.err
    assert "restricted input metadata" in captured.err
    assert "Traceback" not in captured.err
    assert output.read_text(encoding="utf-8") == "previous valid report\n"
