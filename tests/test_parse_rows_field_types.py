"""Public parse_rows must fail cleanly on malformed caller-built CSV cells."""

from __future__ import annotations

from typing import cast

import pytest

from inventory_policy_lab import DataError, parse_rows


HEADER = ["sku", "period", "quantity"]


@pytest.mark.parametrize(
    "bad_header",
    [
        ["sku", None, "quantity"],
        ["sku", 2, "quantity"],
        [b"sku", "period", "quantity"],
        "sku,period,quantity",
        {"sku": "sku", "period": "period", "quantity": "quantity"},
    ],
)
def test_parse_rows_rejects_non_string_fields_in_header(bad_header: object) -> None:
    with pytest.raises(DataError, match="CSV header must be a sequence of string fields") as exc:
        parse_rows(cast(list[list[str]], [bad_header, ["A", "1", "2"]]))
    assert exc.value.exit_code == 4


@pytest.mark.parametrize(
    "bad_row",
    [
        ["A", "1", None],
        ["A", 1, "2"],
        ["A", "1", b"2"],
        ["A", "1", 2.0],
        "A,1,2",
        {"sku": "A", "period": "1", "quantity": "2"},
    ],
)
def test_parse_rows_rejects_non_string_fields_in_data_rows(bad_row: object) -> None:
    with pytest.raises(
        DataError, match=r"line 2: CSV row must be a sequence of string fields"
    ) as exc:
        parse_rows(cast(list[list[str]], [HEADER, bad_row]))
    assert exc.value.exit_code == 4


def test_public_row_type_errors_honor_physical_source_lines() -> None:
    with pytest.raises(DataError, match="line 8: CSV row must be a sequence of string fields"):
        parse_rows(
            cast(list[list[str]], [HEADER, ["A", "1", None]]),
            line_offset=2,
            record_lines=[5, 8],
        )


def test_valid_rows_and_blank_lines_still_parse_unchanged() -> None:
    result = parse_rows(
        [HEADER, ["A", "1", "2"], ["", "", ""], ["A", "2", "3"]]
    )
    assert result.rows == 2
    assert result.calendar == ("1", "2")
    assert result.skus[0].demand == (2.0, 3.0)
