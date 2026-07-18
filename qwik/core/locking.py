"""Cross-platform advisory file locking for store mutations."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import IO, Any

__all__ = ["FileLock"]


class FileLock:
    """Simple advisory lock backed by a sibling file.

    Uses ``fcntl.flock`` on POSIX and ``msvcrt.locking`` on Windows.
    """

    def __init__(self, path: Path, *, timeout: float = 5.0) -> None:
        self._path = path
        self._timeout = timeout
        self._fh: IO[bytes] | None = None

    def acquire(self, *, timeout: float | None = None) -> None:
        deadline = time.monotonic() + (timeout if timeout is not None else self._timeout)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self._path, "a+b")
        while True:
            try:
                if sys.platform == "win32":
                    import msvcrt

                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._fh = fh
                return
            except OSError:
                if time.monotonic() > deadline:
                    fh.close()
                    raise
                time.sleep(0.05)

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt

                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        finally:
            self._fh.close()
            self._fh = None

    def __enter__(self) -> "FileLock":
        self.acquire()
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: Any) -> None:
        self.release()
