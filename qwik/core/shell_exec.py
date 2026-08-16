"""Pick the right interpreter for an already-expanded alias command.

Python's ``subprocess.run(cmd, shell=True)`` does not run the user's
actual interactive shell: on POSIX it always uses ``/bin/sh`` regardless
of ``$SHELL``, and on Windows it always uses ``cmd.exe`` (via
``COMSPEC``) regardless of what the user is typing into. That happens to
line up with :func:`qwik.core.substitute.quote_for_shell`'s POSIX and
``cmd`` quoting rules, but not with PowerShell's: quoting an argument
with PowerShell's ``'...'`` convention and then handing the string to
``cmd.exe`` would be quoting for a shell that never sees it.
"""

from __future__ import annotations

import shutil

__all__ = ["build_invocation"]


def build_invocation(expanded: str, shell: str | None) -> tuple[list[str] | str, bool]:
    """Return ``(command, use_shell)`` for ``subprocess.run`` given *shell*.

    Args:
        expanded: The fully expanded alias command
            (see :func:`qwik.core.substitute.expand`).
        shell: The detected target shell, matching the value passed to
            ``expand(..., shell=...)`` for quoting.

    Returns:
        A ``(command, use_shell)`` pair suitable for
        ``subprocess.run(command, shell=use_shell)``. For every shell
        except ``"pwsh"`` this is ``(expanded, True)``, relying on the
        platform's native ``shell=True`` interpreter (``/bin/sh`` on
        POSIX, ``cmd.exe`` on Windows) — which is exactly what
        ``quote_for_shell`` targets for those shells. For ``"pwsh"`` the
        PowerShell executable is invoked explicitly, since ``shell=True``
        would otherwise run the PowerShell-quoted string through
        ``cmd.exe`` instead.
    """
    if shell == "pwsh":
        exe = "pwsh" if shutil.which("pwsh") else "powershell"
        return [exe, "-NoProfile", "-NonInteractive", "-Command", expanded], False
    return expanded, True
