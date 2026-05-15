"""Windows CMD (best-effort) shell hook renderer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qwik.shells.base import ShellRenderer

if TYPE_CHECKING:
    from qwik.core.models import Alias

__all__ = ["CmdRenderer"]


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

    def render_alias(self, name: str, alias: "Alias") -> str:
        """Return a ``doskey`` macro definition.

        Template aliases are skipped because ``doskey`` cannot interpolate
        positional arguments.

        Args:
            name: Alias identifier.
            alias: The alias definition.

        Returns:
            A ``doskey`` line or an empty string if unsupported.
        """
        from qwik.core.substitute import has_placeholders

        if has_placeholders(alias.command):
            return f"REM omitted {name}: template mode unsupported in cmd"
        return f"doskey {name}={alias.command} $*"
