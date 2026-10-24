"""Regression tests: a generated report must never replace the input CSV."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from conftest import EXAMPLES

from inventory_policy_lab.cli import main


@pytest.mark.parametrize("alias", ["same", "relative", "symlink", "hardlink"])
def test_output_alias_cannot_overwrite_input(
    alias: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "demand.csv"
    source.write_bytes((EXAMPLES / "worked_example.csv").read_bytes())
    before = source.read_bytes()

    if alias == "same":
        destination = source
    elif alias == "relative":
        (tmp_path / "folder").mkdir()
        destination = tmp_path / "folder" / ".." / "demand.csv"
    elif alias == "symlink":
        destination = tmp_path / "alias.csv"
        destination.symlink_to(source)
    else:
        destination = tmp_path / "hardlink.csv"
        os.link(source, destination)

    assert main([str(source), "--holdout", "2", "-o", str(destination)]) == 3
    assert "refusing to overwrite input CSV" in capsys.readouterr().err
    assert source.read_bytes() == before


def test_distinct_output_still_works(tmp_path: Path) -> None:
    source = tmp_path / "demand.csv"
    source.write_bytes((EXAMPLES / "worked_example.csv").read_bytes())
    destination = tmp_path / "report.json"

    assert (
        main(
            [
                str(source),
                "--holdout",
                "2",
                "--format",
                "json",
                "-o",
                str(destination),
            ]
        )
        == 0
    )
    assert "skus" in json.loads(destination.read_text(encoding="utf-8"))
    assert source.read_bytes() == (EXAMPLES / "worked_example.csv").read_bytes()


def test_identity_check_error_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "demand.csv"
    source.write_bytes((EXAMPLES / "worked_example.csv").read_bytes())
    destination = tmp_path / "report.md"

    def deny_samefile(_self: Path, _other: Path) -> bool:
        raise PermissionError("identity check denied")

    monkeypatch.setattr(Path, "samefile", deny_samefile)
    assert main([str(source), "--holdout", "2", "-o", str(destination)]) == 3
    assert "cannot check output" in capsys.readouterr().err
    assert not destination.exists()


def test_atomic_output_preserves_existing_report_on_replace_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "demand.csv"
    source.write_bytes((EXAMPLES / "worked_example.csv").read_bytes())
    destination = tmp_path / "report.md"
    destination.write_text("previous complete report\n", encoding="utf-8")

    def fail_replace(_src: object, _dst: object) -> None:
        raise OSError("replace denied")

    monkeypatch.setattr("inventory_policy_lab.cli.os.replace", fail_replace)

    assert main([str(source), "--holdout", "2", "-o", str(destination)]) == 3
    assert "cannot write" in capsys.readouterr().err
    assert destination.read_text(encoding="utf-8") == "previous complete report\n"
    assert list(tmp_path.glob(".report.md.*.tmp")) == []
