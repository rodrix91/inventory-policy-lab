"""Draw the ABC Pareto chart of the synthetic example as SVG (standard library only).

    python scripts/make_pareto_svg.py           # rewrite docs/abc-pareto.svg
    python scripts/make_pareto_svg.py --check   # exit 1 if the file is stale

Bars are each SKU's share of annual consumption value, largest first, coloured
by ABC class; the line is the cumulative share, with the 80% and 95% class
limits dashed. The numbers come from analysing ``examples/demand_synthetic.csv``
with the default settings, the same run as the README quickstart.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from inventory_policy_lab import analyze_file  # noqa: E402

OUTPUT = ROOT / "docs" / "abc-pareto.svg"
SOURCE = "examples/demand_synthetic.csv"
COLORS = {"A": "#1b6ca8", "B": "#f0a202", "C": "#9aa5b1"}
WIDTH, HEIGHT = 720, 360
LEFT, RIGHT, TOP, BOTTOM = 56, 40, 60, 64


def _xml_label(value: str) -> str:
    """Escape a SKU for an XML 1.0 text node, replacing invalid code points."""
    cleaned = "".join(
        char
        if (
            ord(char) in (9, 10, 13)
            or 0x20 <= ord(char) <= 0xD7FF
            or 0xE000 <= ord(char) <= 0xFFFD
            or 0x10000 <= ord(char) <= 0x10FFFF
        )
        else "\ufffd"
        for char in value
    )
    return escape(cleaned)


def build_svg() -> str:
    report = analyze_file(ROOT / SOURCE)
    items = sorted(report.skus, key=lambda r: (-r.annual_value, r.sku))
    if not items:
        raise ValueError("cannot draw ABC Pareto chart without SKUs")
    if any(not math.isfinite(r.annual_value) or r.annual_value < 0 for r in items):
        raise ValueError("ABC Pareto chart requires finite, non-negative annual values")
    total = sum(r.annual_value for r in items)
    if not math.isfinite(total) or total <= 0:
        raise ValueError("ABC Pareto chart requires a positive, finite total annual value")
    plot_w = WIDTH - LEFT - RIGHT
    plot_h = HEIGHT - TOP - BOTTOM
    step = plot_w / len(items)

    def y(share: float) -> float:
        return TOP + plot_h * (1 - share)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" font-family="sans-serif" font-size="11">',
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#ffffff"/>',
        f'<text x="{LEFT}" y="22" font-size="14" font-weight="bold">'
        "ABC Pareto of annual consumption value (synthetic example data)</text>",
    ]
    for share in (0.0, 0.25, 0.5, 0.75, 1.0):
        parts.append(
            f'<line x1="{LEFT}" y1="{y(share):.1f}" x2="{WIDTH - RIGHT}" y2="{y(share):.1f}" '
            'stroke="#e4e7eb"/>'
        )
        parts.append(
            f'<text x="{LEFT - 6}" y="{y(share) + 4:.1f}" text-anchor="end">{share:.0%}</text>'
        )
    cumulative = 0.0
    points = []
    for index, result in enumerate(items):
        share = result.annual_value / total
        x0 = LEFT + index * step
        parts.append(
            f'<rect x="{x0 + step * 0.15:.1f}" y="{y(share):.1f}" width="{step * 0.7:.1f}" '
            f'height="{plot_h * share:.1f}" fill="{COLORS[result.abc]}"/>'
        )
        label_x = x0 + step / 2
        label = _xml_label(result.sku)
        parts.append(
            f'<text x="{label_x:.1f}" y="{HEIGHT - BOTTOM + 14}" text-anchor="end" '
            f'transform="rotate(-45 {label_x:.1f} {HEIGHT - BOTTOM + 14})">{label}</text>'
        )
        cumulative += share
        points.append(f"{label_x:.1f},{y(cumulative):.1f}")
    for limit in report.config.abc_thresholds:
        parts.append(
            f'<line x1="{LEFT}" y1="{y(limit):.1f}" x2="{WIDTH - RIGHT}" y2="{y(limit):.1f}" '
            'stroke="#c0392b" stroke-dasharray="4 3"/>'
        )
        parts.append(
            f'<text x="{WIDTH - RIGHT + 4}" y="{y(limit) + 4:.1f}" text-anchor="start" '
            f'fill="#c0392b">{limit:.0%}</text>'
        )
    parts.append(
        f'<polyline points="{" ".join(points)}" fill="none" stroke="#222" stroke-width="2"/>'
    )
    legend_x = LEFT + 8
    for offset, (name, color) in enumerate(COLORS.items()):
        x = legend_x + offset * 70
        parts.append(f'<rect x="{x}" y="{TOP - 26}" width="10" height="10" fill="{color}"/>')
        parts.append(f'<text x="{x + 14}" y="{TOP - 17}">class {name}</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Draw docs/abc-pareto.svg.")
    parser.add_argument("--check", action="store_true", help="exit 1 if the file is stale")
    args = parser.parse_args(argv)
    text = build_svg()
    current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else None
    if current == text:
        print("docs/abc-pareto.svg is up to date")
        return 0
    if args.check:
        print("docs/abc-pareto.svg is stale; run scripts/make_pareto_svg.py")
        return 1
    OUTPUT.write_text(text, encoding="utf-8")
    print("wrote docs/abc-pareto.svg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
