"""Windows CMD (best-effort) shell hook renderer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qwik.shells.base import ShellRenderer

if TYPE_CHECKING:
    from pathlib import Path

    from qwik.core.models import Alias

__all__ = ["CmdRenderer"]

# cmd.exe still parses these in the *expanded* macro text, so they must be
# caret-escaped even though the text originates from a doskey macro body.
_CMD_METACHARACTERS = frozenset("&|<>^()%!")


def _escape_doskey_body(command: str) -> str:
    """Escape *command* so it can't break out of a doskey macro definition.

    Two independent substitution passes read a doskey macro's expanded
    text: doskey's own ``$``-prefixed parameter syntax (``$1``-``$9``,
    ``$*``, ``$$``, ``$T``, ``$B``, ``$G``, ``$L``, ...), and then
    cmd.exe's normal command-line parsing of whatever doskey produced.
    Every literal ``$`` is doubled so it can't be misread as a doskey
    substitution, and every cmd.exe metacharacter is caret-escaped so it
    can't act as a command separator/redirect/pipe once expanded.
    """
    escaped = command.replace("$", "$$")
    return "".join("^" + ch if ch in _CMD_METACHARACTERS else ch for ch in escaped)


class CmdRenderer(ShellRenderer):
    """Emit ``cmd.exe`` ``doskey`` macros.

    .. note::
       Template-mode aliases (containing ``{1}`` etc.) are **not**
       supported by ``doskey``.  They are silently omitted from the
       generated hook.  Users on Windows should prefer PowerShell for
       advanced aliases.
    """

    @property
    def shell_name(self) -> str:
        """Return ``'cmd'``."""
        return "cmd"

    def render_header(self) -> str:
        """Return a comment warning about doskey limitations."""
        return "REM qwik cmd hook (best-effort; template aliases omitted)"

    def render_alias(self, name: str, alias: Alias) -> str:
        """Return a ``doskey`` macro definition.

        Template aliases are skipped because ``doskey`` cannot interpolate
        positional arguments. A macro body is also a single physical
        line, so a command containing a newline can't be represented at
        all and is skipped the same way. Every other command is
        caret/dollar-escaped so it can't break out of the macro
        definition (see :func:`_escape_doskey_body`).

        Args:
            name: Alias identifier.
            alias: The alias definition.

        Returns:
            A ``doskey`` line or a ``REM`` comment if unsupported.
        """
        from qwik.core.substitute import has_placeholders

        if has_placeholders(alias.command):
            return f"REM omitted {name}: template mode unsupported in cmd"
        if "\n" in alias.command or "\r" in alias.command:
            return f"REM omitted {name}: multi-line commands unsupported in cmd"
        escaped = _escape_doskey_body(alias.command)
        return f"doskey {name}={escaped} $*"

    def rc_path(self) -> Path | None:
        """Return ``None``; cmd has no rc file."""
        return None

    def install_hook_line(self) -> str | None:
        """Return ``None``; cmd install is unsupported."""
        return None
