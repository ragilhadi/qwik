from pathlib import Path

import pytest

from qwik.core.locking import FileLock, remove_stale_lock


def test_file_lock_exclusive(tmp_path):
    lock = FileLock(tmp_path / "aliases.toml.lock")
    with lock:
        with pytest.raises(OSError):
            FileLock(tmp_path / "aliases.toml.lock").acquire(timeout=0.1)


def test_remove_stale_lock_free_file(tmp_path: Path) -> None:
    lock = tmp_path / "aliases.toml.lock"
    lock.write_text("", encoding="utf-8")
    assert remove_stale_lock(lock) is True
    assert not lock.exists()


def test_remove_stale_lock_missing_file_is_noop(tmp_path: Path) -> None:
    assert remove_stale_lock(tmp_path / "nope.lock") is True


def test_remove_stale_lock_keeps_live_lock(tmp_path: Path) -> None:
    lock = tmp_path / "aliases.toml.lock"
    holder = FileLock(lock)
    with holder:
        assert remove_stale_lock(lock) is False
        assert lock.exists()
    # After release it's stale and removable.
    assert remove_stale_lock(lock) is True
