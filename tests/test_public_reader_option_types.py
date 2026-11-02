"""Malformed public CSV reader settings must fail before opening input files."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from inventory_policy_lab import ConfigError, read_demand


@pytest.mark.parametrize("invalid", [None, False, True, 17, 1.5, [], {}, b"utf-8"])
def test_non_string_encoding_is_a_usage_error_before_reading(
    tmp_path: Path, invalid: object
) -> None:
    missing = tmp_path / "no-such-file.csv"
    with pytest.raises(ConfigError, match="unknown input encoding") as exc:
        read_demand(missing, encoding=cast(str, invalid))
    assert exc.value.exit_code == 2


@pytest.mark.parametrize("invalid", [None, False, True, 17, 1.5, [], {}, b"comma"])
def test_non_string_delimiter_is_a_usage_error_before_reading(
    tmp_path: Path, invalid: object
) -> None:
    missing = tmp_path / "no-such-file.csv"
    with pytest.raises(ConfigError, match="unknown CSV delimiter") as exc:
        read_demand(missing, delimiter=cast(str, invalid))
    assert exc.value.exit_code == 2
