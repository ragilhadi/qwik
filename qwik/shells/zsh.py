"""Zsh shell hook renderer."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from qwik.shells.base import ShellRenderer

if TYPE_CHECKING:
    from qwik.core.models import Alias

__all__ = ["ZshRenderer"]


class ZshRenderer(ShellRenderer):
    """Emit ``zsh`` ``alias`` and function definitions."""

    supports_native_templates = True

    @property
    def shell_name(self) -> str:
        """Return ``'zsh'``."""
        return "zsh"

    def render_alias(self, name: str, alias: Alias) -> str:
        """Return a zsh-compatible alias or function.

        Append-mode logic is identical to
        :class:`~qwik.shells.bash.BashRenderer`.  Template-mode aliases
        become a function referencing zsh's own positional parameters
        where the placeholder grammar translates natively (same mapping as
        bash), falling back to the ``qwik run`` wrapper otherwise.

        Args:
            name: Alias identifier.
            alias: The alias definition.

        Returns:
            Zsh source snippet.
        """
        from qwik.core.substitute import has_placeholders, render_native

        if has_placeholders(alias.command):
            native = render_native(alias.command, "zsh")
            if native is not None:
                return f"{name}() {{\n    {native}\n}}"
            return f'{name}() {{\n    qwik run "{name}" "$@"\n}}'
        escaped = alias.command.replace("'", "'\"'\"'")
        return f"alias {name}='{escaped}'"

    def rc_path(self) -> Path | None:
        """Return ``~/.zshrc``."""
        return Path.home() / ".zshrc"

    def install_hook_line(self) -> str | None:
        """Return the zsh hook line."""
        return '\neval "$(qwik init zsh)"\n'
