"""Fish shell hook renderer."""

from __future__ import annotations

import os
from pathlib import Path
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

    def render_alias(self, name: str, alias: Alias) -> str:
        """Return a fish-compatible alias or function.

        Append-mode aliases become ``alias name 'command'``.
        Template-mode aliases become a wrapper function that calls
        ``qwik run`` so argument substitution is delegated back to the
        Python engine.

        Args:
            name: Alias identifier.
            alias: The alias definition.

        Returns:
            Fish source snippet.
        """
        from qwik.core.substitute import has_placeholders

        if has_placeholders(alias.command):
            return f'function {name}\n    qwik run "{name}" $argv\nend'
        escaped = alias.command.replace("\\", "\\\\").replace("'", "\\'")
        return f"alias {name} '{escaped}'"

    def rc_path(self) -> Path | None:
        """Return the fish config path honoring env overrides."""
        env_val = os.environ.get("__fish_config_dir")
        if env_val:
            return Path(env_val) / "config.fish"
        xdg = os.environ.get("XDG_CONFIG_HOME")
        if xdg:
            return Path(xdg) / "fish" / "config.fish"
        return Path.home() / ".config" / "fish" / "config.fish"

    def install_hook_line(self) -> str | None:
        """Return the fish hook line."""
        return "\nqwik init fish | source -\n"
