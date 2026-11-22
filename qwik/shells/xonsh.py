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

    def render_alias(self, name: str, alias: Alias) -> str:
        """Return a xonsh-compatible alias definition.

        Append-mode aliases become ``aliases["name"] = "command"``.
        Template-mode aliases stay on the list-form
        ``aliases["name"] = ["qwik", "run", name]`` wrapper: native
        splicing would require emitting the raw command text into xonsh's
        own subprocess syntax, whose parsing diverges from POSIX in the
        exact quoting cases the test suite pins (see
        :func:`qwik.core.substitute.render_native`'s exclusion notes), so
        argument substitution keeps delegating to the Python engine.

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
