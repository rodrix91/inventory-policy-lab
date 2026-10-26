"""A reusable Action must not accept an old report as fresh success."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from conftest import ROOT, load_script

run_action = load_script("run_action")


@pytest.mark.parametrize(
    ("mode", "preexisting", "subprocess_code", "expected"),
    [
        ("stale", True, 0, 3),
        ("missing", False, 0, 3),
        ("directory", False, 0, 3),
        ("replaced", True, 0, 0),
        ("created", False, 0, 0),
        ("failure", True, 2, 2),
    ],
)
def test_action_checks_that_a_successful_cli_created_a_new_report(
    mode: str,
    preexisting: bool,
    subprocess_code: int,
    expected: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "demand.csv").write_text("sku,period,demand\nA,2026-01,2\n", encoding="utf-8")
    output = tmp_path / "github-output.txt"
    report = workspace / "reports" / "result.json"
    report.parent.mkdir()
    if preexisting:
        report.write_text('{"stale": true}\n', encoding="utf-8")

    environment = {
        "GITHUB_WORKSPACE": str(workspace),
        "GITHUB_OUTPUT": str(output),
        "INVENTORY_ACTION_PATH": str(ROOT),
        "INVENTORY_INPUT_PATH": "demand.csv",
        "INVENTORY_INPUT_ARGS": "--holdout 2",
        "INVENTORY_INPUT_FORMAT": "json",
        "INVENTORY_INPUT_REPORT_PATH": "reports/result.json",
        "INVENTORY_INPUT_SUMMARY": "true",
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        assert Path(command[-1]) == report
        if mode == "replaced":
            temp = report.with_name("new-result.json")
            temp.write_text('{"fresh": true}\n', encoding="utf-8")
            temp.replace(report)
        elif mode == "directory":
            report.mkdir()
        elif mode == "created":
            report.write_text('{"fresh": true}\n', encoding="utf-8")
        return subprocess.CompletedProcess(command, subprocess_code, "", "")

    with patch.object(run_action.subprocess, "run", side_effect=fake_run) as runner:
        assert run_action.main() == expected
        runner.assert_called_once()

    assert output.read_text(encoding="utf-8") == (
        f"exit-code={expected}\n"
        f"succeeded={'true' if expected == 0 else 'false'}\n"
        f"report-path={report if expected == 0 else ''}\n"
    )
    assert (tmp_path / "summary.md").exists() is (expected == 0)
    if mode in ("stale", "failure"):
        assert report.read_text(encoding="utf-8") == '{"stale": true}\n'
    elif mode == "missing":
        assert not report.exists()
    elif mode == "directory":
        assert report.is_dir()
