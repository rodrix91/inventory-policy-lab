"""Generate the SYNTHETIC example dataset ``examples/demand_synthetic.csv``.

    python scripts/generate_example.py           # rewrite the file
    python scripts/generate_example.py --check   # exit 1 if the file is stale

Every number in the file comes from ``random.Random(SEED)`` below; it is not
real company data. The SKUs are chosen to cover each demand pattern: smooth,
seasonal, erratic, intermittent and lumpy items, one item introduced late, and
one month without a row for an item (to show zero-filling). Lead times are
recorded on some rows only; items without them use the default lead time.
"""

from __future__ import annotations

import argparse
import csv
import io
import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "examples" / "demand_synthetic.csv"
SEED = 20261009
MONTHS = [f"{2024 + m // 12}-{m % 12 + 1:02d}" for m in range(24)]


def _poisson(rng: random.Random, mean: float) -> int:
    """Knuth's Poisson sampler (fine for the small means used here)."""
    limit, k, p = math.exp(-mean), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def _series(rng: random.Random, kind: str) -> list[int]:
    out: list[int] = []
    for m in range(24):
        if kind == "smooth":
            q = rng.gauss(120, 12)
        elif kind == "smooth_small":
            q = rng.gauss(40, 6)
        elif kind == "seasonal":
            q = 80 + 40 * math.sin(2 * math.pi * m / 12) + rng.gauss(0, 8)
        elif kind == "trend":
            q = 30 + 2.5 * m + rng.gauss(0, 5)
        elif kind == "erratic":
            q = rng.choice([20, 25, 30, 150]) + rng.gauss(0, 5)
        elif kind == "intermittent":
            q = (8 + rng.gauss(0, 1.5)) if rng.random() < 0.4 else 0
        elif kind == "lumpy":
            q = rng.choice([2, 5, 40, 90]) if rng.random() < 0.3 else 0
        else:  # "slow": Poisson with a low mean
            q = _poisson(rng, 0.6)
        out.append(max(0, round(q)))
    return out


# sku, pattern, unit cost, observed lead times (periods) or None, first month index
ITEMS: list[tuple[str, str, float, list[float] | None, int]] = [
    ("SKU-001", "smooth", 4.50, [1, 1, 2, 1], 0),
    ("SKU-002", "smooth_small", 22.00, [2, 2, 3, 2], 0),
    ("SKU-003", "seasonal", 9.80, None, 0),
    ("SKU-004", "trend", 15.00, [1, 1, 1], 0),
    ("SKU-005", "erratic", 6.20, [1, 2, 1, 3], 0),
    ("SKU-006", "intermittent", 48.00, [2, 3, 2], 0),
    ("SKU-007", "lumpy", 120.00, [3, 4, 3, 5], 0),
    ("SKU-008", "slow", 310.00, None, 0),
    ("SKU-009", "smooth", 0.85, None, 0),
    ("SKU-010", "intermittent", 12.50, [1, 1, 2], 0),
    ("SKU-011", "smooth_small", 35.00, [2, 2], 14),  # introduced in 2025-03
    ("SKU-012", "lumpy", 7.40, None, 0),
]
SKIPPED_ROW = ("SKU-002", "2024-07")  # no row this month: counted as zero demand


def generate() -> str:
    rng = random.Random(SEED)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["sku", "period", "quantity", "unit_cost", "lead_time"])
    for sku, pattern, cost, leads, start in ITEMS:
        quantities = _series(rng, pattern)
        lead_rows = iter(leads or [])
        for m in range(start, 24):
            if (sku, MONTHS[m]) == SKIPPED_ROW:
                continue
            # a lead time is recorded every sixth month, while observations last
            lead = next(lead_rows, None) if m % 6 == 0 else None
            writer.writerow(
                [sku, MONTHS[m], quantities[m], f"{cost:.2f}", "" if lead is None else f"{lead:g}"]
            )
    return buffer.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the synthetic example dataset.")
    parser.add_argument("--check", action="store_true", help="exit 1 if the file is stale")
    args = parser.parse_args(argv)
    text = generate()
    current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else None
    if current == text:
        print(f"{OUTPUT.relative_to(ROOT)} is up to date")
        return 0
    if args.check:
        print(f"{OUTPUT.relative_to(ROOT)} is stale; run scripts/generate_example.py")
        return 1
    OUTPUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
