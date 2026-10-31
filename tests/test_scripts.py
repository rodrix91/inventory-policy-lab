"""Generated files stay in sync with the scripts that produce them."""

from __future__ import annotations

import csv
import io
import re
import tomllib
from types import SimpleNamespace
from xml.etree import ElementTree

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


@pytest.mark.parametrize(
    "heading",
    [
        "## [0.2.0]",
        "## [0.2.0] - 2026-02-29",
        "## [0.2.0] - 2026-02-30",
        "## [0.2.0] - 2026-04-31",
        "## [0.2.0] - 2026-13-02",
        "## [0.2.0] - 2026-01-02 extra text",
        "## [0.2.0]  - 2026-01-02",
    ],
)
def test_release_notes_fail_closed_on_malformed_release_heading(heading: str) -> None:
    malformed = SAMPLE.replace("## [0.2.0] - 2026-01-02", heading)
    assert release_notes.section(malformed, "0.2.0") is None
    assert release_notes.notes(malformed, "0.2.0") is None


def test_release_notes_reject_duplicate_version_headings() -> None:
    duplicate = SAMPLE + "\\n## [0.2.0] - 2026-01-03\\n\\n- Another section.\\n"
    assert release_notes.section(duplicate, "0.2.0") is None
    assert release_notes.notes(duplicate, "0.2.0") is None
    assert release_notes.section(duplicate, "0.1.0") == "- One."


def test_release_notes_accept_valid_leap_day_and_not_prefix_version() -> None:
    changelog = (
        "# Changelog\\n\\n"
        "## [0.2.0] - 2024-02-29\\n\\n- Released.\\n\\n"
        "## [0.2.0.1] - 2024-03-01\\n\\n- Different release.\\n"
    )
    assert release_notes.section(changelog, "0.2.0") == "- Released."
    assert release_notes.section(changelog, "0.2.0.1") is None
    assert release_notes.section(changelog, "Unreleased") is None


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


def test_pareto_svg_escapes_external_sku_text(monkeypatch: pytest.MonkeyPatch) -> None:
    sku = '<script>alert("invalid")</script> & SKU'
    report = SimpleNamespace(
        skus=[
            SimpleNamespace(sku=sku, annual_value=60.0, abc="A"),
            SimpleNamespace(sku="Another", annual_value=40.0, abc="B"),
        ],
        config=SimpleNamespace(abc_thresholds=(0.8, 0.95)),
    )
    monkeypatch.setattr(make_pareto_svg, "analyze_file", lambda _: report)
    svg = make_pareto_svg.build_svg()
    root = ElementTree.fromstring(svg)
    texts = [element.text for element in root.iter("{http://www.w3.org/2000/svg}text")]
    assert sku in texts
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg and "&amp; SKU" in svg


@pytest.mark.parametrize(
    ("sku", "expected"),
    [
        ("A\x00B", "A\ufffdB"),
        ("A\x08B", "A\ufffdB"),
        ("A\x0bB", "A\ufffdB"),
        ("A\x1fB", "A\ufffdB"),
        ("A\ud800B", "A\ufffdB"),
        ("A\udfffB", "A\ufffdB"),
        ("A\ufffeB", "A\ufffdB"),
        ("A\uffffB", "A\ufffdB"),
        ("A\tB", "A\tB"),
        ("A\nB", "A\nB"),
        ("A\rB", "A\nB"),
        ("A\ue000B", "A\ue000B"),
        ("A\U0001f600B", "A\U0001f600B"),
        ("A<&B", "A<&B"),
    ],
)
def test_pareto_svg_labels_are_valid_xml_10(sku: str, expected: str) -> None:
    rendered = make_pareto_svg._xml_label(sku)
    xml = ElementTree.fromstring(f"<text>{rendered}</text>")
    assert xml.text == expected


def test_pareto_svg_build_survives_control_characters_and_surrogates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_sku = "Item <&\x00\ud800\U0001f600"
    report = SimpleNamespace(
        skus=[SimpleNamespace(sku=raw_sku, annual_value=1.0, abc="A")],
        config=SimpleNamespace(abc_thresholds=(0.8, 0.95)),
    )
    monkeypatch.setattr(make_pareto_svg, "analyze_file", lambda _: report)
    xml = make_pareto_svg.build_svg()
    root = ElementTree.fromstring(xml)
    texts = [element.text for element in root.iter("{http://www.w3.org/2000/svg}text")]
    assert "Item <&\ufffd\ufffd\U0001f600" in texts
    assert "<&" not in xml


@pytest.mark.parametrize(
    ("values", "error"),
    [
        ([], "without SKUs"),
        ([0.0, 0.0], "positive, finite total"),
        ([-1.0, 3.0], "non-negative annual values"),
        ([float("nan"), 3.0], "finite, non-negative annual values"),
        ([float("inf"), 3.0], "finite, non-negative annual values"),
        ([1e308, 1e308], "positive, finite total"),
    ],
)
def test_pareto_svg_rejects_invalid_annual_values(
    monkeypatch: pytest.MonkeyPatch, values: list[float], error: str
) -> None:
    report = SimpleNamespace(
        skus=[
            SimpleNamespace(sku=f"SKU-{i}", annual_value=value, abc="A")
            for i, value in enumerate(values)
        ],
        config=SimpleNamespace(abc_thresholds=(0.8, 0.95)),
    )
    monkeypatch.setattr(make_pareto_svg, "analyze_file", lambda _: report)
    with pytest.raises(ValueError, match=error):
        make_pareto_svg.build_svg()


def test_readme_samples_check_passes() -> None:
    assert load_script("update_readme_samples").main(["--check"]) == 0
