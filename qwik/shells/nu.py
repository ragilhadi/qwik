"""Nushell shell hook renderer."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from qwik.shells.base import ShellRenderer

if TYPE_CHECKING:
    from qwik.core.models import Alias

__all__ = ["NuRenderer"]


class NuRenderer(ShellRenderer):
    """Emit Nushell ``def`` definitions."""

    @property
    def shell_name(self) -> str:
        """Return ``'nu'``."""
        return "nu"

    def render_alias(self, name: str, alias: "Alias") -> str:
        """Return a nushell-compatible function definition.

        Append-mode aliases become ``def name [...args] { ^command ...$args }``.
        Template-mode aliases become a wrapper that delegates to
        ``qwik run`` so that argument substitution is handled by the
        Python engine.

        Args:
            name: Alias identifier.
            alias: The alias definition.

        Returns:
            Nushell source snippet.
        """
        from qwik.core.substitute import has_placeholders

        if has_placeholders(alias.command):
            return f'def {name} [...args] {{\n    qwik run "{name}" ...$args\n}}'
        return f"def {name} [...args] {{\n    ^{alias.command} ...$args\n}}"

    def rc_path(self) -> Path | None:
        """Return the nushell config path honoring env overrides."""
        env_val = os.environ.get("NU_CONFIG_DIR")
        if env_val:
            return Path(env_val) / "config.nu"
        return Path.home() / ".config" / "nushell" / "config.nu"

    def install_hook_line(self) -> str | None:
        """Return the nushell hook line."""
        return "\nsource (qwik init nu | into string)\n"
