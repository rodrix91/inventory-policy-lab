"""Regression coverage for truncated pip hash continuations."""

from pathlib import Path

import pytest

from scripts.check_dev_lock import read_hashed_versions


@pytest.mark.parametrize("trailing", ["", "\n", "    # generated lock metadata\n"])
def test_rejects_dangling_hash_continuation_at_eof(tmp_path: Path, trailing: str) -> None:
    lock = tmp_path / "requirements-dev.lock"
    slash = chr(92)
    digest = "a" * 64
    lock.write_text(
        f"pytest==9.1.1 {slash}\n    --hash=sha256:{digest} {slash}\n" + trailing,
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="dangling line continuation"):
        read_hashed_versions(lock)


def test_complete_hashed_lock_stays_valid(tmp_path: Path) -> None:
    lock = tmp_path / "requirements-dev.lock"
    slash = chr(92)
    digest = "a" * 64
    lock.write_text(
        f"pytest==9.1.1 {slash}\n    --hash=sha256:{digest}\n",
        encoding="utf-8",
    )
    assert read_hashed_versions(lock) == {"pytest": "9.1.1"}
