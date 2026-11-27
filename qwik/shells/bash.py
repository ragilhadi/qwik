"""Bash shell hook renderer."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from qwik.shells.base import ShellRenderer

if TYPE_CHECKING:
    from qwik.core.models import Alias

__all__ = ["BashRenderer"]


class BashRenderer(ShellRenderer):
    """Emit ``bash`` ``alias`` and function definitions."""

    supports_native_templates = True

    @property
    def shell_name(self) -> str:
        """Return ``'bash'``."""
        return "bash"

    def render_alias(self, name: str, alias: Alias) -> str:
        """Return a bash-compatible alias or function.

        Append-mode aliases become ``alias name='command'``.
        Template-mode aliases (containing placeholders) become a function
        that references bash's own positional parameters wherever the
        placeholder grammar translates to native syntax —
        ``gco() { git checkout "$1"; }`` — falling back to the ``qwik run``
        wrapper when the template uses a construct bash cannot express
        natively (a placeholder inside single quotes, ``{0}``-style invalid
        references) so the substitution engine is reused exactly.

        Args:
            name: Alias identifier.
            alias: The alias definition.

        Returns:
            Bash source snippet.
        """
        from qwik.core.substitute import has_placeholders, render_native

        if has_placeholders(alias.command):
            native = render_native(alias.command, "bash")
            if native is not None:
                return f"{name}() {{\n    {native}\n}}"
            # Function wrapper so complex quoting is handled by qwik itself.
            return f'{name}() {{\n    qwik run "{name}" "$@"\n}}'
        escaped = alias.command.replace("'", "'\"'\"'")
        return f"alias {name}='{escaped}'"

    def rc_path(self) -> Path | None:
        """Return ``~/.bashrc``."""
        return Path.home() / ".bashrc"

    def install_hook_line(self) -> str | None:
        """Return the bash hook line."""
        return '\neval "$(qwik init bash)"\n'
