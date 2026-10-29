"""Verify a built wheel and its installed CLI outside the source checkout.

This deliberately uses a fresh virtual environment on the host OS, and drops
PYTHONPATH to catch packaging and console-entry-point regressions that source
tree unit tests alone cannot detect.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    fixture = root / "examples" / "worked_example.csv"
    with tempfile.TemporaryDirectory(prefix="inventory-policy-lab-wheel-") as tmp:
        workspace = Path(tmp)
        wheel_dir = workspace / "dist"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--disable-pip-version-check",
                "--no-deps",
                "--wheel-dir",
                str(wheel_dir),
                str(root),
            ],
            check=True,
        )
        wheels = list(wheel_dir.glob("inventory_policy_lab-*.whl"))
        if len(wheels) != 1:
            raise AssertionError(f"expected one wheel, found: {wheels}")

        venv = workspace / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        binary = venv / ("Scripts" if os.name == "nt" else "bin")
        python = binary / ("python.exe" if os.name == "nt" else "python")
        command = binary / (
            "inventory-policy-lab.exe" if os.name == "nt" else "inventory-policy-lab"
        )
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-deps",
                str(wheels[0]),
            ],
            check=True,
        )
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        version = subprocess.run(
            [
                str(python),
                "-c",
                (
                    "from importlib.metadata import version; "
                    "from pathlib import Path; "
                    "import inventory_policy_lab; "
                    "assert version('inventory-policy-lab') == inventory_policy_lab.__version__; "
                    "assert Path(inventory_policy_lab.__file__).with_name('py.typed').is_file(); "
                    "print(inventory_policy_lab.__version__)"
                ),
            ],
            cwd=workspace,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        cli_version = subprocess.run(
            [str(command), "--version"],
            cwd=workspace,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if cli_version != f"inventory-policy-lab {version}":
            raise AssertionError(f"incorrect installed CLI version: {cli_version!r}")

        result = subprocess.run(
            [
                str(command),
                str(fixture),
                "--holdout",
                "2",
                "--format",
                "json",
            ],
            cwd=workspace,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        report = json.loads(result.stdout)
        if report["tool"] != "inventory-policy-lab" or report["summary"]["skus"] != 2:
            raise AssertionError("installed CLI returned an incomplete inventory policy report")
        if report["settings"]["holdout"] != 2:
            raise AssertionError("installed CLI ignored the requested holdout setting")

    print(f"Clean wheel install and console script: OK ({version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
