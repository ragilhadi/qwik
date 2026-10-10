"""Cross-platform advisory file locking for store mutations."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import IO, Any

__all__ = ["FileLock", "remove_stale_lock"]


class FileLock:
    """Simple advisory lock backed by a sibling file.

    Uses ``fcntl.flock`` on POSIX and ``msvcrt.locking`` on Windows.
    """

    def __init__(self, path: Path, *, timeout: float = 5.0) -> None:
        self._path = path
        self._timeout = timeout
        self._fh: IO[bytes] | None = None

    @property
    def path(self) -> Path:
        """Return the lock file path."""
        return self._path

    def acquire(self, *, timeout: float | None = None) -> None:
        deadline = time.monotonic() + (timeout if timeout is not None else self._timeout)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self._path, "a+b")
        while True:
            try:
                if sys.platform == "win32":
                    import msvcrt

                    # msvcrt.locking() locks a byte range starting at the
                    # file's *current* position. "a+b" opens at EOF, so
                    # without this seek, acquire() and release() (which
                    # seeks to 0) would lock and unlock different byte
                    # ranges — only accidentally symmetric because the
                    # lock file is always empty.
                    fh.seek(0)
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

    def __enter__(self) -> FileLock:
        self.acquire()
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: Any
    ) -> None:
        self.release()


def remove_stale_lock(path: Path) -> bool:
    """Remove *path* if no live process holds the lock; return whether removed.

    A lock file left behind by a crashed process still exists on disk but
    holds no kernel lock, so attempting a non-blocking exclusive flock
    distinguishes the two cases:

    - acquiring the lock succeeds → nobody holds it → the file is stale
      debris and is unlinked (best-effort; on platforms where unlinking
      an open file misbehaves the file may survive, treated as "busy");
    - acquiring fails → a live holder exists → the file is kept.

    On Windows ``msvcrt.locking`` is used for the same probe. Any
    unexpected filesystem error leaves the file untouched and returns
    ``False`` — doctor --fix reports "could not remove" rather than
    deleting something it cannot prove is safe.

    Returns:
        ``True`` if the lock file was removed (or already absent).
    """
    if not path.exists():
        return True
    fh = None
    try:
        fh = open(path, "a+b")
        if sys.platform == "win32":
            import msvcrt

            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        path.unlink(missing_ok=True)
        return True
    except OSError:
        return False
    finally:
        if fh is not None:
            fh.close()
