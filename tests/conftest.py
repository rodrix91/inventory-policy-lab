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


def load_script(name: str) -> ModuleType:
    """Import ``scripts/<name>.py`` as a module (the scripts are not a package)."""
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
