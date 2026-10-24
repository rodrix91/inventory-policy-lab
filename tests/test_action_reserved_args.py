"""The Action must not succeed without analysis or allow CLI output overrides."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from conftest import ROOT, load_script

run_action = load_script("run_action")


@pytest.mark.parametrize(
    "raw",
    [
        "-h",
        "--help",
        "--hel",
        "--version",
        "--ver",
        "--v",
        "--format",
        "--form",
        "--format=json",
        "--for=json",
        "--output",
        "--out",
        "--output=elsewhere.json",
        "--out=elsewhere.json",
        "-o",
        "-oelsewhere.json",
        "--holdout 2 --ver",
    ],
)
def test_rejects_nonexecuting_and_reserved_action_args(raw: str) -> None:
    import shlex

    assert run_action._reserved_argument(shlex.split(raw)) is not None


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "--holdout 2",
        "--rolling-origin",
        "--optimize-cost",
        "--ordering-cost 20",
        "--holding-rate 0.25",
        "--policy RS",
        "--period-safety-stock",
        "--safety-stock bootstrap",
    ],
)
def test_allows_normal_analysis_options(raw: str) -> None:
    import shlex

    assert run_action._reserved_argument(shlex.split(raw)) is None


@pytest.mark.parametrize("bad_args", ["--help", "--ver", "-h", "--for=json", "--out=stolen.md"])
def test_existing_report_does_not_allow_false_green_result(
    bad_args: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    reports = workspace / "reports"
    reports.mkdir(parents=True)
    original = reports / "inventory-report.json"
    original.write_text('{"tool":"old-report"}\n', encoding="utf-8")
    csv = workspace / "demand.csv"
    csv.write_text("sku,period,quantity\nSKU-1,2026-01,5\n", encoding="utf-8")
    outputs = tmp_path / "outputs.txt"

    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    monkeypatch.setenv("INVENTORY_ACTION_PATH", str(ROOT))
    monkeypatch.setenv("INVENTORY_INPUT_PATH", "demand.csv")
    monkeypatch.setenv("INVENTORY_INPUT_ARGS", bad_args)
    monkeypatch.setenv("INVENTORY_INPUT_FORMAT", "json")
    monkeypatch.setenv("INVENTORY_INPUT_REPORT_PATH", "reports/inventory-report.json")
    monkeypatch.setenv("INVENTORY_INPUT_SUMMARY", "false")
    monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))

    with patch.object(run_action.subprocess, "run") as mocked:
        assert run_action.main() == 2
        mocked.assert_not_called()

    assert original.read_text(encoding="utf-8") == '{"tool":"old-report"}\n'
    assert outputs.read_text(encoding="utf-8") == (
        "exit-code=2\nsucceeded=false\nreport-path=\n"
    )
