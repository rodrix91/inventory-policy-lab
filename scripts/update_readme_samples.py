"""Regenerate the sample outputs embedded in README.md from real runs.

Run from the repository root after any change that affects the output:

    python scripts/update_readme_samples.py

Each sample is the fenced block that follows a ``python -m inventory_policy_lab``
command in the README. ``tests/test_readme.py`` fails when they drift apart, so
this script is the fix for those failures. Use ``--check`` to only report.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"

# (arguments, fence language) for every sample in the README, in order.
SAMPLES: list[tuple[list[str], str]] = [
    (["examples/demand_synthetic.csv"], "markdown"),
    (
        [
            "examples/worked_example.csv",
            "--holdout",
            "2",
            "--ordering-cost",
            "30",
            "--holding-rate",
            "0.25",
        ],
        "markdown",
    ),
]


def run_sample(args: list[str]) -> str:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    proc = subprocess.run(
        [sys.executable, "-m", "inventory_policy_lab", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


def pattern_for(args: list[str], lang: str) -> re.Pattern[str]:
    command = re.escape("python -m inventory_policy_lab " + " ".join(args))
    return re.compile(rf"({command}\n```\n\nOutput:\n\n````{lang}\n)(.*?)(````)", re.DOTALL)


def update(text: str) -> str:
    for args, lang in SAMPLES:
        output = run_sample(args)

        def replace(match: re.Match[str], output: str = output) -> str:
            return match.group(1) + output + match.group(3)

        new_text, count = pattern_for(args, lang).subn(replace, text, count=1)
        if count != 1:
            raise SystemExit(f"sample for {' '.join(args)!r} not found in README.md")
        text = new_text
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Regenerate the README samples.")
    parser.add_argument("--check", action="store_true", help="exit 1 if samples are stale")
    args = parser.parse_args(argv)
    current = README.read_text(encoding="utf-8")
    updated = update(current)
    if updated == current:
        print("README samples are up to date")
        return 0
    if args.check:
        print("README samples are stale; run scripts/update_readme_samples.py")
        return 1
    README.write_text(updated, encoding="utf-8")
    print("README samples updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
