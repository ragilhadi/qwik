import pytest
from qwik.core.locking import FileLock


def test_file_lock_exclusive(tmp_path):
    lock = FileLock(tmp_path / "aliases.toml.lock")
    with lock:
        with pytest.raises(OSError):
            FileLock(tmp_path / "aliases.toml.lock").acquire(timeout=0.1)
