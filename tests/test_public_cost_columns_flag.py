"""The public optional-cost flag requires an actual boolean, never truthiness."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from inventory_policy_lab import ConfigError, parse_rows, read_demand


@pytest.mark.parametrize("invalid", [None, 0, 1, 0.0, 1.0, "", "false", "true", b"false", [], {}])
def test_read_demand_rejects_nonboolean_cost_flag_before_open(
    tmp_path: Path, invalid: object
) -> None:
    absent = tmp_path / "not-present.csv"
    with pytest.raises(ConfigError, match="cost_columns must be a boolean") as exc:
        read_demand(absent, cost_columns=cast(bool, invalid))
    assert exc.value.exit_code == 2


@pytest.mark.parametrize("invalid", [None, 0, 1, 0.0, 1.0, "", "false", "true", b"false", [], {}])
def test_parse_rows_rejects_nonboolean_cost_flag(invalid: object) -> None:
    records = [
        ["sku", "period", "quantity", "order_cost"],
        ["A", "1", "2", "7"],
    ]
    with pytest.raises(ConfigError, match="cost_columns must be a boolean") as exc:
        parse_rows(records, cost_columns=cast(bool, invalid))
    assert exc.value.exit_code == 2


def test_valid_true_and_false_preserve_opt_in_cost_behavior() -> None:
    records = [
        ["sku", "period", "quantity", "order_cost"],
        ["A", "1", "2", "7"],
    ]
    assert parse_rows(records, cost_columns=False).skus[0].order_cost is None
    assert parse_rows(records, cost_columns=True).skus[0].order_cost == 7.0
