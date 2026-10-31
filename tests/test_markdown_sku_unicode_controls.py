"""Untrusted SKU identifiers remain literal in JSON and visible in Markdown."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from inventory_policy_lab import Config, analyze_file, render_json, render_markdown
from inventory_policy_lab.render import _md_text


def test_all_terminal_controls_and_directional_marks_use_visible_markers() -> None:
    controls = (*range(32), *range(127, 160))
    bidi = (0x061C, 0x200E, 0x200F, *range(0x202A, 0x202F), *range(0x2066, 0x2070))
    invisible = (0x00AD, 0x200B, 0x2060, 0xFEFF, 0x2028, 0x2029)
    for codepoint in (*controls, *bidi, *invisible):
        original = f"SKU{chr(codepoint)}WEST"
        rendered = _md_text(original)
        if codepoint in (10, 13):
            assert rendered == f"SKU&#{codepoint};WEST"
        else:
            assert rendered == f"SKU[U+{codepoint:04X}]WEST"
        assert chr(codepoint) not in rendered


def test_unsafe_unicode_sku_stays_visible_across_tables_and_lossless_in_json(
    tmp_path: Path,
) -> None:
    sku = "West\u202e[verified]\u2066\x00\x1b\u0085\u200b\ufeff\u2028\u2029"
    path = tmp_path / "demand.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("sku", "period", "quantity", "unit_cost"))
        for period in range(1, 13):
            writer.writerow((sku, period, 10, 12))

    report = analyze_file(path, Config(holdout=2))
    markdown = render_markdown(report)
    rendered = _md_text(sku)
    assert markdown.count(rendered) >= 2
    for codepoint in (0x202E, 0x2066, 0, 27, 133, 0x200B, 0xFEFF, 0x2028, 0x2029):
        assert f"[U+{codepoint:04X}]" in markdown
        assert chr(codepoint) not in markdown
    assert json.loads(render_json(report))["skus"][0]["sku"] == sku


def test_multilingual_joiners_remain_intact() -> None:
    label = "São Paulo 日本語 क्\u200dषि\u200c مشتری"
    assert _md_text(label) == label
