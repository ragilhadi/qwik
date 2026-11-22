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
    supports_completions = True

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

    def render_completion_alias(self, name: str, alias: Alias) -> str:
        """Return the zsh completion definition for *name*, if declared."""
        from qwik.shells.completions import zsh_completion

        return zsh_completion(name, alias)

    def render_cd_refresh_footer(self) -> str:
        """Re-render the hook on directory change (zsh: chpwd hook)."""
        return (
            "# qwik project layer: re-resolve .qwik.toml on directory change\n"
            "__qwik_project_refresh() {\n"
            '    eval "$(qwik init zsh 2>/dev/null)"\n'
            "}\n"
            "autoload -Uz add-zsh-hook\n"
            "add-zsh-hook chpwd __qwik_project_refresh"
        )

    def rc_path(self) -> Path | None:
        """Return ``~/.zshrc``."""
        return Path.home() / ".zshrc"

    def install_hook_line(self) -> str | None:
        """Return the zsh hook line."""
        return '\neval "$(qwik init zsh)"\n'
