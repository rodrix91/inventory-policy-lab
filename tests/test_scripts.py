"""Generated files stay in sync with the scripts that produce them."""

from __future__ import annotations

import csv
import io
import re
import tomllib

import pytest
from conftest import ROOT, load_script

release_notes = load_script("release_notes")
generate_example = load_script("generate_example")
make_pareto_svg = load_script("make_pareto_svg")

SAMPLE = """# Changelog

## [Unreleased]

## [0.2.0] - 2026-01-02

### Added

- Two.

## [0.1.0] - 2026-01-01

- One.

[0.2.0]: https://example.com/0.2.0
"""


def test_release_notes_section_and_link() -> None:
    notes = release_notes.notes(SAMPLE, "0.2.0")
    assert notes.startswith("### Added\n\n- Two.\n\nFull changelog: https://github.com/")
    assert release_notes.section(SAMPLE, "0.1.0") == "- One."
    assert release_notes.notes(SAMPLE, "9.9.9") is None
    assert release_notes.section("## [Unreleased]\n", "Unreleased") is None


def test_release_notes_cli(capsys: pytest.CaptureFixture[str]) -> None:
    with open(ROOT / "pyproject.toml", "rb") as handle:
        version = tomllib.load(handle)["project"]["version"]
    assert release_notes.main([f"v{version}"]) == 0
    assert "Full changelog" in capsys.readouterr().out
    assert release_notes.main(["9.9.9"]) == 1
    assert release_notes.main([]) == 2


def test_synthetic_example_is_reproducible_and_labelled() -> None:
    text = generate_example.generate()
    assert text == (ROOT / "examples" / "demand_synthetic.csv").read_text(encoding="utf-8")
    rows = list(csv.DictReader(io.StringIO(text)))
    assert {row["sku"] for row in rows} == {f"SKU-{i:03d}" for i in range(1, 13)}
    assert "SYNTHETIC" in (generate_example.__doc__ or "")
    assert generate_example.main(["--check"]) == 0


def test_pareto_svg_is_up_to_date() -> None:
    svg = make_pareto_svg.build_svg()
    assert svg == (ROOT / "docs" / "abc-pareto.svg").read_text(encoding="utf-8")
    assert svg.startswith("<svg") and "synthetic example data" in svg
    assert len(re.findall(r"<rect x=\"[\d.]+\" y=\"[\d.]+\" width=\"[\d.]+\" height", svg)) >= 12
    assert make_pareto_svg.main(["--check"]) == 0


def test_readme_samples_check_passes() -> None:
    assert load_script("update_readme_samples").main(["--check"]) == 0
