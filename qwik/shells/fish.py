"""Fish shell hook renderer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qwik.shells.base import ShellRenderer

if TYPE_CHECKING:
    from qwik.core.models import Alias

__all__ = ["FishRenderer"]


class FishRenderer(ShellRenderer):
    """Emit ``fish`` ``alias`` and function definitions."""

    @property
    def shell_name(self) -> str:
        """Return ``'fish'``."""
        return "fish"

    def render_alias(self, name: str, alias: "Alias") -> str:
        """Return a fish-compatible alias or function.

        Append-mode aliases become ``alias name 'command'``.
        Template-mode aliases become a wrapper function that calls
        ``qwik -r`` so argument substitution is delegated back to the
        Python engine.

        Args:
            name: Alias identifier.
            alias: The alias definition.

        Returns:
            Fish source snippet.
        """
        from qwik.core.substitute import has_placeholders

        if has_placeholders(alias.command):
            return f"function {name}\n" f'    qwik -r "{name}" $argv\n' f"end"
        escaped = alias.command.replace("'", "\\'")
        return f"function {name}\n" f"    {escaped} $argv\n" f"end"
