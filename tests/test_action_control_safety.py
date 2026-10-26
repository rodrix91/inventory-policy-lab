"""Security regressions for the reusable Action's external inputs and summary."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from conftest import ROOT, load_script

run_action = load_script("run_action")


@pytest.mark.parametrize("control", ["\n", "\r", "\x00", "\x07", "\x08", "\x1b", "\x7f", "\x85"])
@pytest.mark.parametrize("label", ["input path", "report-path", "args"])
def test_action_controls_fail_closed(control: str, label: str) -> None:
    with pytest.raises(ValueError, match="line breaks|terminal control characters"):
        run_action._reject_input_controls(
            f"safe{control}unsafe", label, allow_tab=label == "args"
        )


def test_tab_is_only_allowed_for_shell_argument_separation() -> None:
    run_action._reject_input_controls("--holdout\t2", "args", allow_tab=True)
    for label in ("input path", "report-path"):
        with pytest.raises(ValueError, match="terminal control characters"):
            run_action._reject_input_controls("part\tpart.csv", label)


@pytest.mark.parametrize("label", ["input path", "report-path", "args"])
# Environment variables cannot contain NUL; the direct guard covers it separately.
@pytest.mark.parametrize("control", ["\n", "\x1b", "\x7f", "\x85"])
def test_main_rejects_unsafe_values_before_subprocess_or_report_directory(
    control: str, label: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "demand.csv").write_text(
        "sku,period,demand\nA,2026-01,2\n", encoding="utf-8"
    )
    outputs = tmp_path / "outputs.txt"
    values = {
        "INVENTORY_INPUT_PATH": "demand.csv",
        "INVENTORY_INPUT_ARGS": "--holdout 2",
        "INVENTORY_INPUT_REPORT_PATH": "reports/report.json",
    }
    changed = {
        "input path": "INVENTORY_INPUT_PATH",
        "report-path": "INVENTORY_INPUT_REPORT_PATH",
        "args": "INVENTORY_INPUT_ARGS",
    }[label]
    values[changed] = f"{values[changed]}{control}malicious"
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
    monkeypatch.setenv("INVENTORY_ACTION_PATH", str(ROOT))
    monkeypatch.setenv("INVENTORY_INPUT_FORMAT", "json")
    monkeypatch.setenv("INVENTORY_INPUT_SUMMARY", "false")
    with patch.object(run_action.subprocess, "run") as mocked:
        assert run_action.main() == 2
        mocked.assert_not_called()
    assert not (workspace / "reports").exists()
    assert outputs.read_text(encoding="utf-8") == (
        "exit-code=2\nsucceeded=false\nreport-path=\n"
    )


def test_valid_argument_tabs_are_still_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "demand.csv").write_text(
        "sku,period,demand\nA,2026-01,2\n", encoding="utf-8"
    )
    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    monkeypatch.setenv("INVENTORY_ACTION_PATH", str(ROOT))
    monkeypatch.setenv("INVENTORY_INPUT_PATH", "demand.csv")
    monkeypatch.setenv("INVENTORY_INPUT_ARGS", "--holdout\t2")
    monkeypatch.setenv("INVENTORY_INPUT_REPORT_PATH", "reports/result.json")
    monkeypatch.setenv("INVENTORY_INPUT_FORMAT", "json")
    monkeypatch.setenv("INVENTORY_INPUT_SUMMARY", "false")

    def complete(command: list[str], **_kwargs: object):
        assert command[4:6] == ["--holdout", "2"]
        Path(command[-1]).write_text("{}\n", encoding="utf-8")
        return run_action.subprocess.CompletedProcess(command, 0, "", "")

    with patch.object(run_action.subprocess, "run", side_effect=complete):
        assert run_action.main() == 0


@pytest.mark.parametrize("run_length", [0, 3, 6])
def test_json_summary_fence_cannot_be_closed_by_untrusted_data(
    run_length: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = {"sku": "SKU " + chr(96) * run_length + " trouble"}
    source = json.dumps(payload)
    report = tmp_path / "report.json"
    report.write_text(source + "\n", encoding="utf-8")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    run_action._write_summary(report, "json")

    fence = chr(96) * max(3, run_length + 1)
    expected = f"## inventory-policy-lab\n\n{fence}json\n{source}\n{fence}\n"
    assert summary.read_text(encoding="utf-8") == expected
    assert json.loads(source) == payload
