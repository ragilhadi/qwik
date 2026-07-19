"""Shell detection helpers.

The functions here infer the current user's shell from environment
variables and (on Linux) from ``/proc``. They are used by
``qwik doctor`` and by the conflict-check pipeline in
``qwik add``/``qwik rename`` to pick the right builtin set.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["shell_name_from_env", "shell_name_from_proc", "detect_shell"]


def shell_name_from_env() -> str | None:
    """Return shell name from ``$SHELL`` if present.

    Returns:
        A lowercase shell name (``bash``, ``zsh``, ``fish``, ``pwsh``),
        or ``None`` if ``$SHELL`` is unset or unrecognised.
    """
    shell_env = os.environ.get("SHELL", "").lower()
    if "bash" in shell_env:
        return "bash"
    if "zsh" in shell_env:
        return "zsh"
    if "fish" in shell_env:
        return "fish"
    if "pwsh" in shell_env or "powershell" in shell_env:
        return "pwsh"
    return None


def shell_name_from_proc() -> str | None:
    """Return shell name by inspecting parent process on Linux.

    Reads ``/proc/self/status`` to find the parent PID and resolves
    its executable. On non-Linux systems or any failure, returns
    ``None``.

    Returns:
        A lowercase shell name, or ``None`` if it cannot be determined.
    """
    try:
        with Path("/proc/self/status").open(encoding="utf-8") as f:
            for line in f:
                if line.startswith("PPid:"):
                    ppid = line.split()[1]
                    exe_link = Path(f"/proc/{ppid}/exe")
                    if exe_link.exists():
                        name = exe_link.resolve().name.lower()
                        if "bash" in name:
                            return "bash"
                        if "zsh" in name:
                            return "zsh"
                        if "fish" in name:
                            return "fish"
                        if "pwsh" in name or "powershell" in name:
                            return "pwsh"
    except Exception:
        pass
    return None


def detect_shell() -> str | None:
    """Attempt to detect the current user's shell.

    Returns:
        A lowercase shell name (e.g. ``bash``, ``zsh``), or ``None``.
    """
    return shell_name_from_env() or shell_name_from_proc()