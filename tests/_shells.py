"""Shared shell-binary resolution for integration test modules.

Windows runners put the WSL launcher stub (``C:\\Windows\\System32\\bash.exe``)
ahead of Git for Windows' bin directory on PATH; that stub prints "install a
WSL distribution" and exits regardless of what's installed, which an
integration test would otherwise read as "bash ran and failed" instead of
"bash is a shim".  Every test module that invokes a real shell uses this.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

__all__ = ["resolve_shell_binary"]

_WINDOWS_GIT_BASH_CANDIDATES = (
    r"C:\Program Files\Git\bin\bash.exe",
    r"C:\Program Files\Git\usr\bin\bash.exe",
)


def resolve_shell_binary(name: str) -> str | None:
    """Resolve *name* to the binary to invoke, working around PATH quirks."""
    if name == "bash" and sys.platform == "win32":
        for candidate in _WINDOWS_GIT_BASH_CANDIDATES:
            if Path(candidate).exists():
                return candidate
    return shutil.which(name)
