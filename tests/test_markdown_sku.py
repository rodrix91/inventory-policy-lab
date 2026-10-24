"""Regression coverage for SKU presentation in Markdown inventory reports."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

from inventory_policy_lab import Config, analyze_file, render_json, render_markdown

ROOT = Path(__file__).resolve().parents[1]


def _write_history(path: Path, sku: str) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("sku", "period", "quantity", "unit_cost"))
        for period in range(1, 13):
            writer.writerow((sku, period, 10 + period % 3, 12))


def test_literal_sku_in_main_and_backtest_tables_preserves_json(tmp_path: Path) -> None:
    sku = "AB|[invoice](https://example.invalid)<b> &"
    path = tmp_path / "inventory.csv"
    _write_history(path, sku)
    report = analyze_file(path, Config(holdout=2))
    markdown = render_markdown(report)
    escaped = r"AB\|\[invoice\]\(https://example.invalid\)&lt;b&gt; &amp;"
    assert markdown.count("| " + escaped + " |") >= 2
    assert "[invoice](https://example.invalid)" not in markdown
    assert "<b>" not in markdown
    assert json.loads(render_json(report))["skus"][0]["sku"] == sku


def test_multiline_sku_is_one_markdown_source_line_across_replays(tmp_path: Path) -> None:
    sku = "AB\n## VERIFIED\r\n![bad](https://example.invalid)"
    path = tmp_path / "replay.csv"
    _write_history(path, sku)
    config = Config(
        holdout=2,
        test_periods=2,
        order_cost=2.0,
        holding_cost=0.25,
        stockout_cost=5.0,
        bootstrap_samples=100,
    )
    report = analyze_file(path, config)
    markdown = render_markdown(report)
    assert "&#10;" in markdown and "&#13;" in markdown
    assert "\n## VERIFIED" not in markdown
    assert r"\!\[bad\]\(https://example.invalid\)" in markdown
    assert "## Out-of-sample replay" in markdown
    assert "### Cost of the test periods" in markdown
    assert json.loads(render_json(report))["skus"][0]["sku"] == sku


def test_cli_sku_escaping_without_changing_machine_readable_values(tmp_path: Path) -> None:
    sku = "P|[click](https://example.invalid)"
    path = tmp_path / "cli.csv"
    _write_history(path, sku)
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    args = [sys.executable, "-m", "inventory_policy_lab", str(path), "--holdout", "2"]
    markdown = subprocess.run(
        args, cwd=ROOT, env=env, capture_output=True, text=True, check=False
    )
    data = subprocess.run(
        [*args, "--format", "json"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert markdown.returncode == 0, markdown.stderr
    assert data.returncode == 0, data.stderr
    assert r"P\|\[click\]\(https://example.invalid\)" in markdown.stdout
    assert json.loads(data.stdout)["skus"][0]["sku"] == sku
