"""The command line: output formats, files, options and exit codes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import EXAMPLES, run_module, write_csv

from inventory_policy_lab import __version__
from inventory_policy_lab.cli import main

WORKED = str(EXAMPLES / "worked_example.csv")


def test_markdown_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([WORKED, "--holdout", "2"]) == 0
    assert capsys.readouterr().out.startswith("# Inventory policy report\n")


def test_json_to_a_file_with_every_option(tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    code = main(
        [
            WORKED,
            "--format",
            "json",
            "-o",
            str(out),
            "--holdout",
            "2",
            "--service-level",
            "0.9",
            "--class-service-levels",
            "a=0.99,B=0.95",
            "--lead-time",
            "2",
            "--lead-time-std",
            "0.5",
            "--review-period",
            "0",
            "--ordering-cost",
            "30",
            "--holding-rate",
            "0.25",
            "--order-cover",
            "2",
            "--sigma",
            "rmse",
            "--abc-thresholds",
            "0.7,0.9",
            "--xyz-thresholds",
            "0.4,0.8",
            "--periods-per-year",
            "52",
            "--ma-window",
            "2",
            "--ses-alpha",
            "0.3",
            "--croston-alpha",
            "0.2",
        ]
    )
    assert code == 0
    settings = json.loads(out.read_text(encoding="utf-8"))["settings"]
    assert settings["class_service_levels"] == {"A": 0.99, "B": 0.95}
    assert settings["abc_thresholds"] == [0.7, 0.9]
    assert settings["review_period"] == 0
    assert settings["periods_per_year"] == 52
    assert settings["sigma"] == "rmse"


def test_unwritable_output_is_exit_3(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([WORKED, "--holdout", "2", "-o", str(tmp_path / "missing" / "r.md")]) == 3
    assert "cannot write" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("args", "code", "message"),
    [
        (["missing.csv"], 3, "file not found"),
        ([WORKED, "--holdout", "7"], 5, "needs at least 9"),
        ([WORKED, "--holdout", "2", "--service-level", "1"], 2, "service_level must be"),
        ([WORKED, "--holdout", "2", "--ordering-cost", "5"], 2, "EOQ needs both"),
    ],
)
def test_library_errors_map_to_exit_codes(
    args: list[str], code: int, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(args) == code
    err = capsys.readouterr().err
    assert err.startswith("inventory-policy-lab: error: ")
    assert message in err


def test_data_error_is_exit_4(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write_csv(tmp_path / "bad.csv", "sku,quantity\na,1\n")
    assert main([str(path)]) == 4
    assert "missing required column" in capsys.readouterr().err


@pytest.mark.parametrize(
    "args",
    [
        ["--abc-thresholds", "0.8"],
        ["--abc-thresholds", "a,b"],
        ["--class-service-levels", "A0.9"],
        ["--class-service-levels", "A=high"],
        ["--format", "html"],
    ],
)
def test_bad_option_values_are_usage_errors(
    args: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main([WORKED, *args])
    assert excinfo.value.code == 2
    assert "error:" in capsys.readouterr().err


def test_version_and_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == f"inventory-policy-lab {__version__}"
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "exit codes:" in capsys.readouterr().out


def test_python_dash_m_runs_the_cli() -> None:
    proc = run_module(WORKED, "--holdout", "2", "--format", "json")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["skus"][0]["sku"] == "W-1"
    proc = run_module("does-not-exist.csv")
    assert proc.returncode == 3
    assert proc.stdout == ""


def test_bootstrap_options(capsys: pytest.CaptureFixture[str]) -> None:
    args = [WORKED, "--holdout", "2", "--safety-stock", "bootstrap"]
    assert main([*args, "--bootstrap-samples", "500", "--seed", "3", "--format", "json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["settings"]["safety_stock_method"] == "bootstrap"
    assert (report["settings"]["bootstrap_samples"], report["settings"]["seed"]) == (500, 3)
    assert {s["policy"]["safety_stock_method"] for s in report["skus"]} == {"bootstrap"}
    assert main(args) == 0
    assert "bootstrap of protection-interval demand (2000 samples, seed 0)" in (
        capsys.readouterr().out
    )
    assert main([*args, "--bootstrap-samples", "10"]) == 2
    assert "bootstrap samples must be at least 100" in capsys.readouterr().err


def test_test_periods_option(capsys: pytest.CaptureFixture[str]) -> None:
    synthetic = str(EXAMPLES / "demand_synthetic.csv")
    assert main([synthetic, "--test-periods", "12", "--format", "json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["settings"]["test_periods"] == 12
    assert report["out_of_sample"]["summary"]["normal"]["out_of_sample"]["fill_rate"] == 0.9443
    assert main([synthetic, "--test-periods", "20"]) == 5
    assert "Lower --test-periods or --holdout" in capsys.readouterr().err
