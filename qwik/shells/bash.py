"""Bash shell hook renderer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qwik.shells.base import ShellRenderer

if TYPE_CHECKING:
    from qwik.core.models import Alias

__all__ = ["BashRenderer"]


class BashRenderer(ShellRenderer):
    """Emit ``bash`` ``alias`` and function definitions."""

    @property
    def shell_name(self) -> str:
        """Return ``'bash'``."""
        return "bash"

    def render_alias(self, name: str, alias: "Alias") -> str:
        """Return a bash-compatible alias or function.

        Append-mode aliases become ``alias name='command'``.
        Template-mode aliases (containing placeholders) become a
        wrapper function that delegates to ``qwik run`` so that the
        substitution engine is reused exactly.

        Args:
            name: Alias identifier.
            alias: The alias definition.

        Returns:
            Bash source snippet.
        """
        from qwik.core.substitute import has_placeholders

        if has_placeholders(alias.command):
            # Function wrapper so complex quoting is handled by qwik itself.
            return f"{name}() {{\n" f'    qwik run "{name}" "$@"\n' f"}}"
        escaped = alias.command.replace("'", "'\"'\"'")
        return f"alias {name}='{escaped}'"
