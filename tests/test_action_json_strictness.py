"""GitHub Action JSON validation must reject ambiguous keys and nonfinite data."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import load_script, valid_action_report_json

run_action = load_script("run_action")


def _write(tmp_path: Path, payload: str) -> Path:
    path = tmp_path / "action-report.json"
    path.write_text(payload, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("original", "replacement"),
    [
        ('"rows": 1', '"rows": 1, "rows": 999'),
        ('"skus": 1', '"skus": 1, "skus": 999'),
        ('"forecast": {}', '"forecast": {}, "forecast": {}'),
        ('"rows": 1', r'"rows": 1, "\u0072ows": 999'),
        ('"forecast": {}', r'"forecast": {}, "\u0066orecast": {}'),
    ],
)
def test_rejects_duplicate_json_properties_at_any_depth(
    tmp_path: Path, original: str, replacement: str
) -> None:
    clean = valid_action_report_json()
    assert original in clean
    corrupted = clean.replace(original, replacement, 1)
    # Standard Python JSON would accept it by silently keeping the last key.
    assert json.loads(corrupted) != json.loads(clean) or original.startswith('"forecast"')
    assert not run_action._valid_report_file(_write(tmp_path, corrupted), "json")


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity", "1e999", "-1e999"])
@pytest.mark.parametrize("container", ["settings", "forecast", "simulation"])
def test_rejects_nonfinite_json_numbers_even_inside_ignored_metadata(
    tmp_path: Path, number: str, container: str
) -> None:
    clean = valid_action_report_json()
    original = f'"{container}": {{}}'
    assert original in clean
    corrupted = clean.replace(original, f'"{container}": {{"untrusted": {number}}}', 1)
    assert not run_action._valid_report_file(_write(tmp_path, corrupted), "json")


@pytest.mark.parametrize("number", ["1e308", "-1e308", "0.125", "-0.0", "1e-999"])
def test_finite_json_numbers_in_optional_metadata_remain_accepted(
    tmp_path: Path, number: str
) -> None:
    clean = valid_action_report_json()
    corrupted = clean.replace('"settings": {}', f'"settings": {{"scale": {number}}}', 1)
    assert run_action._valid_report_file(_write(tmp_path, corrupted), "json")


def test_legitimate_cli_json_output_is_still_valid(tmp_path: Path) -> None:
    from conftest import EXAMPLES, run_module

    result = run_module(str(EXAMPLES / "demand_synthetic.csv"), "--format", "json")
    assert result.returncode == 0, result.stderr
    assert run_action._valid_report_file(_write(tmp_path, result.stdout), "json")


def test_strict_json_validation_does_not_change_markdown_behavior(tmp_path: Path) -> None:
    from conftest import EXAMPLES, run_module

    result = run_module(str(EXAMPLES / "demand_synthetic.csv"), "--format", "markdown")
    assert result.returncode == 0, result.stderr
    assert run_action._valid_report_file(_write(tmp_path, result.stdout), "markdown")
