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


def _path_has_open_fd(p: Path) -> bool:
    """True if *p* is held open by any fd of this process (Linux only)."""
    fd_dir = Path("/proc/self/fd")
    if not fd_dir.is_dir():
        return False
    for fd in fd_dir.iterdir():
        try:
            if fd.resolve() == p:
                return True
        except OSError:
            continue
    return False


def test_remove_stale_lock_closes_handle_before_unlink(tmp_path: Path, monkeypatch) -> None:
    """Regression: the probe handle must be closed before unlinking.

    Windows refuses to delete a file that any process still has open
    (WinError 32), so unlinking while the FileLock probe's handle is
    still open makes remove_stale_lock fail on every call there. This
    pins the close-then-unlink ordering (verified via /proc on Linux;
    other platforms merely run the happy path).
    """
    import qwik.core.locking as locking

    lock = tmp_path / "aliases.toml.lock"
    lock.write_text("", encoding="utf-8")

    real_unlink = Path.unlink
    fd_state_at_unlink: list[bool] = []

    def spy_unlink(path_self: Path, *args: object, **kwargs: object) -> None:
        fd_state_at_unlink.append(_path_has_open_fd(lock))
        real_unlink(path_self)  # type: ignore[arg-type]

    monkeypatch.setattr("pathlib.Path.unlink", spy_unlink)
    assert locking.remove_stale_lock(lock) is True
    if fd_state_at_unlink and Path("/proc/self/fd").is_dir():
        assert fd_state_at_unlink == [False], "lock file was still open (would fail on Windows)"
