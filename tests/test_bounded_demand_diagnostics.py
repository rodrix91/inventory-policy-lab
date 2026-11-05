"""Untrusted demand CSV cells must not flood or forge CLI diagnostics."""

from __future__ import annotations

from pathlib import Path

import pytest

from inventory_policy_lab import DataError, parse_rows, read_demand
from inventory_policy_lab.cli import main


def _rows(column: str, value: str, *, sku: str = "A") -> list[list[str]]:
    header = [
        "sku",
        "period",
        "quantity",
        "unit_cost",
        "lead_time",
        "order_cost",
        "stockout_cost",
    ]
    row = [sku, "1", "3", "2", "1", "4", "5"]
    row[header.index(column)] = value
    return [header, row]


@pytest.mark.parametrize(
    ("column", "value", "expected"),
    [
        ("quantity", "secret-" + "X" * 15000 + "-private-tail", "not a number"),
        ("unit_cost", "1e" + "9" * 15000, "not a finite number"),
        ("lead_time", "private-" + "Q" * 12000 + "-tail", "not a number"),
        ("order_cost", "1e" + "9" * 12000, "not a finite number"),
        ("stockout_cost", "bad-" + "Z" * 12000 + "-tail", "not a number"),
    ],
    ids=[
        "bad-quantity",
        "overflow-cost",
        "bad-lead-time",
        "overflow-order",
        "bad-stockout",
    ],
)
def test_numeric_failures_bound_csv_cell_values(
    column: str, value: str, expected: str
) -> None:
    with pytest.raises(DataError, match=expected) as caught:
        parse_rows(_rows(column, value), cost_columns=True)
    message = str(caught.value)
    assert len(message) < 400
    assert "[truncated]" in message
    assert "-private-tail" not in message
    assert "X" * 200 not in message
    assert "Z" * 200 not in message
    assert "9" * 200 not in message


@pytest.mark.parametrize(
    "column",
    ["quantity", "unit_cost", "lead_time", "order_cost", "stockout_cost"],
    ids=["quantity", "unit-cost", "lead-time", "order-cost", "stockout-cost"],
)
def test_negative_finite_long_numbers_have_bounded_diagnostics(column: str) -> None:
    negative = "-1." + "0" * 15000
    with pytest.raises(DataError, match="negative " + column) as caught:
        parse_rows(_rows(column, negative), cost_columns=True)
    message = str(caught.value)
    assert "[truncated]" in message
    assert len(message) < 400
    assert "0" * 200 not in message


def test_period_and_sku_errors_do_not_echo_long_names() -> None:
    period = "invalid-" + "A" * 15000 + "-period-tail"
    with pytest.raises(DataError, match="period") as caught:
        parse_rows(_rows("period", period))
    assert len(str(caught.value)) < 400
    assert "[truncated]" in str(caught.value)
    assert "-period-tail" not in str(caught.value)

    sku = "sensitive-" + "B" * 15000 + "-sku-tail"
    with pytest.raises(DataError, match="empty quantity") as caught:
        parse_rows(_rows("quantity", "", sku=sku))
    assert len(str(caught.value)) < 400
    assert "[truncated]" in str(caught.value)
    assert "-sku-tail" not in str(caught.value)


def test_large_sku_in_negative_and_overflow_messages_is_bounded() -> None:
    sku = "company-" + "C" * 15000 + "-private-tail"
    with pytest.raises(DataError, match="negative quantity") as caught:
        parse_rows(_rows("quantity", "-2", sku=sku))
    assert len(str(caught.value)) < 400
    assert "-private-tail" not in str(caught.value)
    assert "[truncated]" in str(caught.value)

    rows = [
        ["sku", "period", "quantity"],
        [sku, "1", "1e308"],
        [sku, "1", "1e308"],
    ]
    with pytest.raises(DataError, match="exceeds the finite numeric range") as caught:
        parse_rows(rows)
    assert len(str(caught.value)) < 400
    assert "[truncated]" in str(caught.value)
    assert "-private-tail" not in str(caught.value)


def test_existing_short_error_wording_stays_stable() -> None:
    with pytest.raises(DataError) as caught:
        parse_rows(_rows("quantity", "not-a-number"))
    assert str(caught.value) == "line 2: quantity 'not-a-number' is not a number"
    with pytest.raises(DataError) as caught:
        parse_rows(_rows("unit_cost", "-3"))
    assert str(caught.value) == "line 2: negative unit_cost -3"
    with pytest.raises(DataError) as caught:
        parse_rows(_rows("period", "invalid"))
    assert str(caught.value) == (
        "line 2: period 'invalid' is not YYYY-MM, YYYY-MM-DD or an integer"
    )


def test_cli_fails_without_exposing_hidden_suffix_or_replacing_prior_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "supplier.csv"
    source.write_text(
        "sku,period,quantity\nA,1," + "private-" + "X" * 12000 + "-secret-tail\n",
        encoding="utf-8",
    )
    previous = tmp_path / "verified.json"
    original = '{"trusted":true}\n'
    previous.write_text(original, encoding="utf-8")
    assert main([str(source), "--format", "json", "--output", str(previous)]) == 4
    output = capsys.readouterr()
    assert "is not a number" in output.err
    assert "[truncated]" in output.err
    assert "-secret-tail" not in output.err
    assert len(output.err) < 500
    assert not output.out
    assert previous.read_text(encoding="utf-8") == original
