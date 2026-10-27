"""Workspace-boundary regression checks for the reusable GitHub Action."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from conftest import ROOT, load_script, valid_action_report_json

run_action = load_script("run_action")


def test_nested_input_within_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "workspace"
    directory = root / "exports"
    directory.mkdir(parents=True)
    source = directory / "demand.csv"
    source.write_text("sku,period,demand\nSKU1,2026-01,5\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_WORKSPACE", str(root))
    assert run_action._resolve_input_path("exports/demand.csv") == source.resolve()
    assert run_action._resolve_input_path("exports/../exports/demand.csv") == source.resolve()


def test_missing_workspace_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)
    with pytest.raises(ValueError, match="GITHUB_WORKSPACE is required"):
        run_action._resolve_input_path("demand.csv")


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("-", "must name a CSV"),
        ("demand\n.csv", "line breaks"),
        ("demand\r.csv", "line breaks"),
    ],
)
def test_rejects_stdin_and_line_breaks(
    raw: str, message: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path))
    with pytest.raises(ValueError, match=message):
        run_action._resolve_input_path(raw)


def test_rejects_absolute_path_inside_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path))
    with pytest.raises(ValueError, match="must be relative"):
        run_action._resolve_input_path(str(tmp_path / "demand.csv"))


def test_rejects_parent_traversal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setenv("GITHUB_WORKSPACE", str(root))
    with pytest.raises(ValueError, match="stay within"):
        run_action._resolve_input_path("../outside.csv")


def test_rejects_symlink_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "private.csv"
    outside.write_text("private data\n", encoding="utf-8")
    link = workspace / "linked.csv"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Creating symlinks is not supported on this runner")
    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    with pytest.raises(ValueError, match="stay within"):
        run_action._resolve_input_path("linked.csv")


def test_runner_rejects_unsafe_path_before_any_side_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outputs = tmp_path / "github-output.txt"
    report = workspace / "reports" / "report.json"
    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    monkeypatch.setenv("INVENTORY_INPUT_PATH", "../secret.csv")
    monkeypatch.setenv("INVENTORY_INPUT_ARGS", "--holdout 2")
    monkeypatch.setenv("INVENTORY_INPUT_FORMAT", "json")
    monkeypatch.setenv("INVENTORY_INPUT_REPORT_PATH", "reports/report.json")
    monkeypatch.setenv("INVENTORY_INPUT_SUMMARY", "false")
    monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
    with patch.object(run_action.subprocess, "run") as mocked:
        assert run_action.main() == 2
        mocked.assert_not_called()
    assert not report.parent.exists()
    assert outputs.read_text(encoding="utf-8") == ("exit-code=2\nsucceeded=false\nreport-path=\n")


def test_runner_passes_valid_workspace_input_to_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / "demand.csv"
    source.write_text("sku,period,demand\nSKU1,2026-01,5\n", encoding="utf-8")
    outputs = tmp_path / "github-output.txt"
    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    monkeypatch.setenv("INVENTORY_ACTION_PATH", str(ROOT))
    monkeypatch.setenv("INVENTORY_INPUT_PATH", "demand.csv")
    monkeypatch.setenv("INVENTORY_INPUT_ARGS", "--holdout 2")
    monkeypatch.setenv("INVENTORY_INPUT_FORMAT", "json")
    monkeypatch.setenv("INVENTORY_INPUT_REPORT_PATH", "reports/report.json")
    monkeypatch.setenv("INVENTORY_INPUT_SUMMARY", "false")
    monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        assert command[3] == str(source.resolve())
        assert command[4:6] == ["--holdout", "2"]
        output = Path(command[-1])
        output.write_text(valid_action_report_json(), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    with patch.object(run_action.subprocess, "run", side_effect=fake_run) as mocked:
        assert run_action.main() == 0
        mocked.assert_called_once()
    assert outputs.read_text(encoding="utf-8") == (
        f"exit-code=0\nsucceeded=true\nreport-path={workspace / 'reports' / 'report.json'}\n"
    )
