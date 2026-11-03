"""The Action must not advertise newly written but incomplete inventory reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from conftest import EXAMPLES, load_script, run_module, valid_action_report_json

run_action = load_script("run_action")


@pytest.fixture
def json_report(tmp_path: Path) -> Path:
    path = tmp_path / "report.json"
    path.write_text(valid_action_report_json(), encoding="utf-8")
    return path


def test_valid_synthetic_report_and_real_cli_outputs(tmp_path: Path, json_report: Path) -> None:
    assert run_action._valid_report_file(json_report, "json")
    for fmt in ("json", "markdown"):
        result = run_module(
            str(EXAMPLES / "demand_synthetic.csv"),
            "--format",
            fmt,
        )
        assert result.returncode == 0, result.stderr
        output = tmp_path / ("real." + ("json" if fmt == "json" else "md"))
        output.write_text(result.stdout, encoding="utf-8")
        assert run_action._valid_report_file(output, fmt)


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("top", "tool", "not-the-inventory-tool"),
        ("top", "version", None),
        ("top", "version", ""),
        ("top", "source", None),
        ("top", "source", ""),
        ("top", "rows", True),
        ("top", "rows", 0),
        ("top", "periods", True),
        ("top", "periods", 0),
        ("top", "first_period", None),
        ("top", "last_period", None),
        ("top", "settings", None),
        ("top", "summary", None),
        ("top", "skus", None),
        ("top", "skus", []),
        ("top", "skus", ["not an object"]),
        ("summary", "skus", None),
        ("summary", "skus", True),
        ("summary", "skus", 2),
        ("summary", "abc_xyz", None),
        ("summary", "overall_fill_rate", None),
        ("summary", "overall_fill_rate", True),
        ("summary", "overall_fill_rate", -0.1),
        ("summary", "overall_fill_rate", 1.1),
        ("summary", "overall_fill_rate", float("nan")),
        ("summary", "overall_fill_rate", float("inf")),
        ("item", "sku", None),
        ("item", "sku", ""),
        ("item", "periods", None),
        ("item", "periods", True),
        ("item", "periods", 0),
        ("item", "forecast", None),
        ("item", "policy", None),
        ("item", "simulation", None),
    ],
)
def test_rejects_incomplete_or_contradictory_json_report(
    json_report: Path, section: str, key: str, value: Any
) -> None:
    payload = json.loads(valid_action_report_json())
    if section == "top":
        payload[key] = value
    elif section == "summary":
        payload["summary"][key] = value
    else:
        payload["skus"][0][key] = value
    json_report.write_text(json.dumps(payload), encoding="utf-8")
    assert not run_action._valid_report_file(json_report, "json")


def test_all_zero_demand_reports_retain_their_legitimate_null_fill_rate(
    json_report: Path,
) -> None:
    payload = json.loads(valid_action_report_json())
    payload["summary"]["overall_fill_rate"] = None
    payload["skus"][0]["simulation"].update(total_demand=0.0, served_from_stock=0.0, fill_rate=None)
    json_report.write_text(json.dumps(payload), encoding="utf-8")
    assert run_action._valid_report_file(json_report, "json")
    payload["skus"][0]["simulation"]["total_demand"] = 5.0
    json_report.write_text(json.dumps(payload), encoding="utf-8")
    assert not run_action._valid_report_file(json_report, "json")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("total_demand", None),
        ("total_demand", -1),
        ("total_demand", True),
        ("total_demand", "10"),
        ("total_demand", 10**400),
        ("served_from_stock", None),
        ("served_from_stock", -1),
        ("served_from_stock", True),
        ("served_from_stock", 11.0),
        ("served_from_stock", 10**400),
        ("fill_rate", None),
        ("fill_rate", -0.1),
        ("fill_rate", 1.1),
        ("fill_rate", "1"),
        ("fill_rate", 10**400),
        ("fill_rate", 0.25),
    ],
)
def test_action_rejects_invalid_simulation_counts_and_ratios(
    json_report: Path, field: str, value: Any
) -> None:
    report = json.loads(valid_action_report_json())
    report["skus"][0]["simulation"][field] = value
    json_report.write_text(json.dumps(report), encoding="utf-8")
    assert not run_action._valid_report_file(json_report, "json"), (field, value)


def test_action_rejects_false_global_fill_rate_and_accepts_rounded_data(
    json_report: Path,
) -> None:
    report = json.loads(valid_action_report_json())
    for false_rate in (0.0, 0.25, 0.9, 10**400):
        report["summary"]["overall_fill_rate"] = false_rate
        json_report.write_text(json.dumps(report), encoding="utf-8")
        assert not run_action._valid_report_file(json_report, "json")

    report["summary"]["overall_fill_rate"] = 0.6667
    report["skus"][0]["simulation"].update(
        total_demand=3.0, served_from_stock=2.0, fill_rate=0.6667
    )
    json_report.write_text(json.dumps(report), encoding="utf-8")
    assert run_action._valid_report_file(json_report, "json")


def test_action_checks_aggregate_weighted_fill_rate_across_skus(
    json_report: Path,
) -> None:
    report = json.loads(valid_action_report_json())
    first = report["skus"][0]
    first["simulation"].update(total_demand=9.0, served_from_stock=9.0, fill_rate=1.0)
    second = json.loads(json.dumps(first))
    second["sku"] = "B"
    second["simulation"].update(total_demand=1.0, served_from_stock=0.0, fill_rate=0.0)
    report["skus"].append(second)
    report["summary"]["skus"] = 2
    report["summary"]["overall_fill_rate"] = 0.9
    json_report.write_text(json.dumps(report), encoding="utf-8")
    assert run_action._valid_report_file(json_report, "json")

    # 0.5 is the unweighted average; the CLI reports the demand-weighted rate.
    report["summary"]["overall_fill_rate"] = 0.5
    json_report.write_text(json.dumps(report), encoding="utf-8")
    assert not run_action._valid_report_file(json_report, "json")


def test_action_retains_valid_very_small_rounded_simulations(json_report: Path) -> None:
    report = json.loads(valid_action_report_json())
    report["skus"][0]["simulation"].update(total_demand=0.0, served_from_stock=0.0, fill_rate=1.0)
    # A positive demand below 0.00005 rounds to zero in the published JSON;
    # the original nonzero overall rate cannot be reconstructed from it.
    report["summary"]["overall_fill_rate"] = 1.0
    json_report.write_text(json.dumps(report), encoding="utf-8")
    assert run_action._valid_report_file(json_report, "json")

def test_rejects_duplicate_skus_and_malformed_json(tmp_path: Path, json_report: Path) -> None:
    payload = json.loads(valid_action_report_json())
    payload["skus"].append(dict(payload["skus"][0]))
    payload["summary"]["skus"] = 2
    json_report.write_text(json.dumps(payload), encoding="utf-8")
    assert not run_action._valid_report_file(json_report, "json")
    for content in ("{", "[]", "null", '{"tool":"inventory-policy-lab"}', ""):
        json_report.write_text(content, encoding="utf-8")
        assert not run_action._valid_report_file(json_report, "json")
    missing = tmp_path / "missing.json"
    assert not run_action._valid_report_file(missing, "json")
    assert not run_action._valid_report_file(tmp_path, "json")
    json_report.write_bytes(b"\xff")
    assert not run_action._valid_report_file(json_report, "json")


def test_rejects_partial_markdown_and_accepts_real_one(tmp_path: Path) -> None:
    result = run_module(str(EXAMPLES / "demand_synthetic.csv"), "--format", "markdown")
    assert result.returncode == 0, result.stderr
    path = tmp_path / "report.md"
    source = result.stdout
    path.write_text(source, encoding="utf-8")
    assert run_action._valid_report_file(path, "markdown")
    invalid = (
        "",
        "# Inventory policy report\n",
        "Inventory policy report\n\n" + source.split("\n\n", 1)[1],
        source[:-1],
        source.replace("\n## ABC-XYZ matrix\n", "\n## Unknown matrix\n"),
        source.replace("\n## Demand patterns (Syntetos-Boylan)\n", "\n## Unknown patterns\n"),
        source.replace("\n## Policy per SKU\n", "\n## Unknown SKU section\n"),
        source.replace("\n## Forecast backtest (", "\n## Unknown backtest ("),
    )
    for modified in invalid:
        path.write_text(modified, encoding="utf-8")
        assert not run_action._valid_report_file(path, "markdown")
