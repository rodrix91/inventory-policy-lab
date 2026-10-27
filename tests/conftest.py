"""Shared helpers: the repository root and a runner for ``python -m inventory_policy_lab``."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"


def run_module(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    """Run the package as a subprocess, the way a user does."""
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    return subprocess.run(
        [sys.executable, "-m", "inventory_policy_lab", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def write_csv(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def valid_action_report_json() -> str:
    """Minimal structurally valid synthetic report for Action boundary tests."""
    import json

    return (
        json.dumps(
            {
                "tool": "inventory-policy-lab",
                "version": "0.10.0",
                "source": "synthetic-test.csv",
                "rows": 1,
                "periods": 1,
                "first_period": "2026-01",
                "last_period": "2026-01",
                "settings": {},
                "summary": {
                    "skus": 1,
                    "abc_xyz": {"A": {"X": 1, "Y": 0, "Z": 0}},
                    "overall_fill_rate": 1.0,
                },
                "skus": [
                    {
                        "sku": "A",
                        "periods": 1,
                        "forecast": {},
                        "policy": {},
                        "simulation": {},
                    }
                ],
            }
        )
        + "\n"
    )


def load_script(name: str) -> ModuleType:
    """Import ``scripts/<name>.py`` as a module (the scripts are not a package)."""
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
