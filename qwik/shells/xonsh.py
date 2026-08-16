"""Xonsh shell hook renderer."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from qwik.shells.base import ShellRenderer

if TYPE_CHECKING:
    from qwik.core.models import Alias

__all__ = ["XonshRenderer"]


class XonshRenderer(ShellRenderer):
    """Emit xonsh alias definitions."""

    @property
    def shell_name(self) -> str:
        """Return ``'xonsh'``."""
        return "xonsh"

    def render_alias(self, name: str, alias: "Alias") -> str:
        """Return a xonsh-compatible alias definition.

        Append-mode aliases become ``aliases["name"] = "command"``.
        Template-mode aliases become a list-form alias,
        ``aliases["name"] = ["qwik", "run", "name"]`` — xonsh appends
        any arguments given at the command line to a list alias, so
        argument substitution is delegated back to the Python engine
        without needing a Python function (whose body would otherwise
        need to invoke a subprocess through xonsh's own subprocess
        syntax, which ``qwik run(...)`` is not).

        Args:
            name: Alias identifier.
            alias: The alias definition.

        Returns:
            Xonsh source snippet.
        """
        from qwik.core.substitute import has_placeholders

        if has_placeholders(alias.command):
            return f'aliases["{name}"] = ["qwik", "run", "{name}"]'
        escaped = alias.command.replace("\\", "\\\\").replace('"', '\\"')
        return f'aliases["{name}"] = "{escaped}"'

    def rc_path(self) -> Path | None:
        """Return the xonsh rc path honoring env overrides."""
        env_val = os.environ.get("XONSHRC")
        if env_val:
            return Path(env_val)
        return Path.home() / ".xonshrc"

    def install_hook_line(self) -> str | None:
        """Return the xonsh hook line."""
        return "\nexecx($(qwik init xonsh))\n"
