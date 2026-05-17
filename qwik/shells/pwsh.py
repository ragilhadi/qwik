"""PowerShell shell hook renderer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qwik.shells.base import ShellRenderer

if TYPE_CHECKING:
    from qwik.core.models import Alias

__all__ = ["PwshRenderer"]


class PwshRenderer(ShellRenderer):
    """Emit PowerShell function definitions."""

    @property
    def shell_name(self) -> str:
        """Return ``'pwsh'``."""
        return "pwsh"

    def render_alias(self, name: str, alias: "Alias") -> str:
        """Return a PowerShell function definition.

        All aliases are rendered as functions because PowerShell does not
        support passing arbitrary arguments to native ``alias``.
        Template mode uses ``qwik run``; append mode forwards ``$args``
        directly.

        Args:
            name: Alias identifier.
            alias: The alias definition.

        Returns:
            PowerShell source snippet.
        """
        from qwik.core.substitute import has_placeholders

        if has_placeholders(alias.command):
            return f'function {name} {{\n    qwik run "{name}" @args\n}}'
        return f"function {name} {{\n    {alias.command} @args\n}}"
