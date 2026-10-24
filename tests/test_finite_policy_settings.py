"""Non-finite inventory configuration must fail before a report is written."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from conftest import EXAMPLES

from inventory_policy_lab import Config, ConfigError
from inventory_policy_lab.cli import main

WORKED = str(EXAMPLES / "worked_example.csv")


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("periods_per_year", float("nan")),
        ("periods_per_year", float("inf")),
        ("lead_time", float("nan")),
        ("lead_time", float("inf")),
        ("lead_time_std", float("nan")),
        ("lead_time_std", float("-inf")),
        ("review_period", float("nan")),
        ("review_period", float("inf")),
        ("order_cover", float("nan")),
        ("order_cover", float("inf")),
        ("ordering_cost", float("nan")),
        ("ordering_cost", float("inf")),
        ("holding_rate", float("nan")),
        ("holding_rate", float("inf")),
        ("abc_thresholds", (0.8, float("inf"))),
        ("xyz_thresholds", (0.5, float("inf"))),
        ("xyz_thresholds", (float("nan"), 1.0)),
    ],
)
def test_api_rejects_nonfinite_settings(setting: str, value: float | tuple[float, float]) -> None:
    changes: dict[str, Any] = {setting: value}
    config = replace(Config(), **changes)
    with pytest.raises(ConfigError, match="must be finite"):
        config.validate()


@pytest.mark.parametrize(
    ("args", "error"),
    [
        (["--lead-time", "NaN"], "lead time must be finite"),
        (["--lead-time-std", "inf"], "lead time standard deviation must be finite"),
        (["--review-period", "NaN"], "review period must be finite"),
        (["--order-cover", "inf"], "order cover must be finite"),
        (["--periods-per-year", "inf"], "periods per year must be finite"),
        (["--xyz-thresholds", "0.5,inf"], "second XYZ threshold must be finite"),
        (
            ["--ordering-cost", "inf", "--holding-rate", "0.2"],
            "ordering cost must be finite",
        ),
        (
            ["--ordering-cost", "10", "--holding-rate", "NaN"],
            "holding rate must be finite",
        ),
    ],
)
def test_cli_fails_closed_without_overwriting_existing_report(
    args: list[str],
    error: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "prior-report.json"
    output.write_text("previous valid report\n", encoding="utf-8")
    code = main([WORKED, "--holdout", "2", "--format", "json", "-o", str(output), *args])
    captured = capsys.readouterr()
    assert code == 2
    assert error in captured.err
    assert captured.out == ""
    assert output.read_text(encoding="utf-8") == "previous valid report\n"


def test_finite_policy_settings_still_validate() -> None:
    Config(
        lead_time=0,
        lead_time_std=0,
        review_period=0,
        order_cover=0.5,
        ordering_cost=12,
        holding_rate=0.25,
        xyz_thresholds=(0.5, 1.0),
    ).validate()
