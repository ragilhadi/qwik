"""Zsh shell hook renderer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qwik.shells.base import ShellRenderer

if TYPE_CHECKING:
    from qwik.core.models import Alias

__all__ = ["ZshRenderer"]


class ZshRenderer(ShellRenderer):
    """Emit ``zsh`` ``alias`` and function definitions."""

    @property
    def shell_name(self) -> str:
        """Return ``'zsh'``."""
        return "zsh"

    def render_alias(self, name: str, alias: "Alias") -> str:
        """Return a zsh-compatible alias or function.

        Logic is identical to :class:`~qwik.shells.bash.BashRenderer`.

        Args:
            name: Alias identifier.
            alias: The alias definition.

        Returns:
            Zsh source snippet.
        """
        from qwik.core.substitute import has_placeholders

        if has_placeholders(alias.command):
            return f"{name}() {{\n" f'    qwik -r "{name}" "$@"\n' f"}}"
        escaped = alias.command.replace("'", "'\"'\"'")
        return f"alias {name}='{escaped}'"
