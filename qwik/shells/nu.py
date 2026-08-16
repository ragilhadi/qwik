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

        Both append-mode and template-mode aliases delegate to
        ``qwik run``. Nushell's ``^command`` syntax runs exactly one
        external program with argument-list semantics — it has no
        built-in way to safely hand it an arbitrary, possibly
        shell-operator-laden command *string* the way POSIX shells or
        PowerShell's ``[ScriptBlock]::Create`` do, so splicing the raw
        command text into the function body (the previous approach) let
        a stray ``}`` in the command close the function early. Routing
        through ``qwik run`` reuses the shell-aware quoting/execution
        that command already needs for template mode.

        Args:
            name: Alias identifier.
            alias: The alias definition.

        Returns:
            Nushell source snippet.
        """
        return f'def {name} [...args] {{\n    qwik run "{name}" ...$args\n}}'

    def rc_path(self) -> Path | None:
        """Return the nushell config path honoring env overrides."""
        env_val = os.environ.get("NU_CONFIG_DIR")
        if env_val:
            return Path(env_val) / "config.nu"
        return Path.home() / ".config" / "nushell" / "config.nu"

    def install_hook_line(self) -> str | None:
        """Return the nushell hook line."""
        return "\nsource (qwik init nu | into string)\n"
