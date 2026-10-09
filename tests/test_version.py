"""The version is declared twice; keep both in sync and in the CHANGELOG."""

from __future__ import annotations

import re
import tomllib

from conftest import ROOT

import inventory_policy_lab
from inventory_policy_lab import __version__


def test_package_version_matches_pyproject() -> None:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        assert tomllib.load(handle)["project"]["version"] == __version__


def test_changelog_has_an_entry_for_the_version() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert re.search(
        rf"^## \[{re.escape(__version__)}\] - \d{{4}}-\d{{2}}-\d{{2}}$", changelog, re.M
    )


def test_public_api_names_exist() -> None:
    for name in inventory_policy_lab.__all__:
        assert hasattr(inventory_policy_lab, name), name
