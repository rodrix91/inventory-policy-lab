"""The README shows real output: every sample must match a fresh run."""

from __future__ import annotations

import re

import pytest
from conftest import ROOT, load_script, run_module

samples = load_script("update_readme_samples")

README = (ROOT / "README.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(("args", "lang"), samples.SAMPLES)
def test_readme_sample_matches_a_real_run(args: list[str], lang: str) -> None:
    match = samples.pattern_for(args, lang).search(README)
    assert match, f"README has no sample for {args}"
    proc = run_module(*args)
    assert proc.returncode == 0, proc.stderr
    assert match.group(2) == proc.stdout, "stale sample: run scripts/update_readme_samples.py"


def test_readme_states_the_version_and_status() -> None:
    from inventory_policy_lab import __version__

    assert f"version {__version__}" in README.lower() or f"v{__version__}" in README
    assert re.search(r"status.*alpha", README, re.IGNORECASE)


def test_readme_python_example_runs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    block = re.search(r"```python\n(.*?)```", README, re.DOTALL)
    assert block
    monkeypatch.chdir(ROOT)
    namespace: dict[str, object] = {}
    exec(compile(block.group(1), "README.md", "exec"), namespace)
    assert str(namespace["markdown"]).startswith("# Inventory policy report")
    assert capsys.readouterr().out.count("SKU-") == 12
