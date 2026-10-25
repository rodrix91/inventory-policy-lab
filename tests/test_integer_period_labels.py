"""Integer period spellings must agree with canonical calendar labels."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import write_csv

from inventory_policy_lab import parse_rows, read_demand
from inventory_policy_lab.cli import main


def test_padded_integer_periods_use_canonical_calendar_and_aggregate() -> None:
    data = parse_rows(
        [
            ["sku", "period", "quantity", "lead_time"],
            ["A", "01", "2", "3"],
            ["A", "1", "4", ""],
            ["A", "002", "5", "2"],
            ["B", "-0", "1", ""],
            ["B", "00", "2", ""],
        ]
    )
    assert data.period_kind == "integer"
    assert data.calendar == ("0", "1", "2")
    first, second = data.skus
    assert first.sku == "A"
    assert first.periods == ("1", "2")
    assert first.demand == (6, 5)
    assert first.lead_time_periods == ("1", "2")
    assert second.sku == "B"
    assert second.periods == ("0", "1", "2")
    assert second.demand == (3, 0, 0)


@pytest.mark.parametrize(
    ("spellings", "canonical"),
    [
        (("0003", "3"), ("3",)),
        (("-01", "-1"), ("-1",)),
        (("-0", "0"), ("0",)),
    ],
)
def test_equivalent_integer_labels_are_one_period(
    spellings: tuple[str, str], canonical: tuple[str, ...]
) -> None:
    data = parse_rows(
        [
            ["sku", "period", "quantity"],
            ["A", spellings[0], "2"],
            ["A", spellings[1], "3"],
        ]
    )
    assert data.calendar == canonical
    assert data.skus[0].demand == (5,)


def test_padded_integer_file_is_accepted_by_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    content = "sku,period,quantity\n" + "".join(
        f"A,{period:02d},5\n" for period in range(1, 9)
    )
    source = write_csv(tmp_path / "padded.csv", content)
    assert read_demand(source).calendar == tuple(str(i) for i in range(1, 9))
    assert main([str(source), "--holdout", "2", "--format", "json"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out)["skus"][0]["sku"] == "A"
