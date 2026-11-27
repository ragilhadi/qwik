"""Fish shell hook renderer."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from qwik.shells.base import ShellRenderer

if TYPE_CHECKING:
    from qwik.core.models import Alias

__all__ = ["FishRenderer"]

_RC_NAME = "config.fish"


class FishRenderer(ShellRenderer):
    """Emit ``fish`` ``alias`` and function definitions."""

    supports_native_templates = True
    supports_completions = True

    @property
    def shell_name(self) -> str:
        """Return ``'fish'``."""
        return "fish"

    def render_alias(self, name: str, alias: Alias) -> str:
        """Return a fish-compatible alias or function.

        Append-mode aliases become ``alias name 'command'``.
        Template-mode aliases become a function referencing ``$argv``
        where the placeholder grammar translates to native fish syntax,
        falling back to a wrapper that calls ``qwik run`` otherwise, so
        argument substitution stays with the Python engine for constructs
        fish cannot express safely.

        Args:
            name: Alias identifier.
            alias: The alias definition.

        Returns:
            Fish source snippet.
        """
        from qwik.core.substitute import has_placeholders, render_native

        if has_placeholders(alias.command):
            native = render_native(alias.command, "fish")
            if native is not None:
                return f"function {name}\n    {native}\nend"
            return f'function {name}\n    qwik run "{name}" $argv\nend'
        escaped = alias.command.replace("\\", "\\\\").replace("'", "\\'")
        return f"alias {name} '{escaped}'"

    def render_completion_alias(self, name: str, alias: Alias) -> str:
        """Return the fish completion definition for *name*, if declared."""
        from qwik.shells.completions import fish_completion

        return fish_completion(name, alias)

    def rc_path(self) -> Path | None:
        """Return the fish config path honoring env overrides."""
        env_val = os.environ.get("__fish_config_dir")
        if env_val:
            return Path(env_val) / _RC_NAME
        xdg = os.environ.get("XDG_CONFIG_HOME")
        if xdg:
            return Path(xdg) / "fish" / _RC_NAME
        return Path.home() / ".config" / "fish" / _RC_NAME

    def install_hook_line(self) -> str | None:
        """Return the fish hook line."""
        return "\nqwik init fish | source -\n"
