"""Abstract base class and per-shell renderers for shell hook generation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qwik.core.models import Alias

__all__ = [
    "ShellRenderer",
    "get_renderer",
    "SUPPORTED_SHELLS",
]

SUPPORTED_SHELLS: tuple[str, ...] = ("bash", "zsh", "fish", "pwsh", "cmd")


class ShellRenderer(ABC):
    """ABC for emitting shell-native alias definitions.

    Each concrete subclass must produce syntax that, when evaluated by
    the target shell, makes every *enabled* alias callable as a real
    command (either via ``alias`` or via a wrapper function).
    """

    @property
    @abstractmethod
    def shell_name(self) -> str:
        """Return the canonical shell identifier."""
        ...

    @abstractmethod
    def render_alias(self, name: str, alias: "Alias") -> str:
        """Return a single alias/function definition for *name*.

        Args:
            name: Alias identifier.
            alias: The alias definition.

        Returns:
            A string containing shell-native code (e.g. ``alias gs='git status'``).
        """
        ...

    def render_header(self) -> str:
        """Return an optional header emitted before alias definitions.

        Returns:
            A comment or shell directive.  Defaults to an empty string.
        """
        return ""

    def render_footer(self) -> str:
        """Return an optional footer emitted after alias definitions.

        Returns:
            A comment or shell directive.  Defaults to an empty string.
        """
        return ""

    def render_all(self, aliases: dict[str, "Alias"]) -> str:
        """Render a complete hook snippet for the given alias map.

        Only **enabled** aliases are included.  Output is sorted by name
        for stable generation.

        Args:
            aliases: Mapping from alias name to :class:`~qwik.core.models.Alias`.

        Returns:
            The full shell script text.
        """
        lines: list[str] = []
        header = self.render_header()
        if header:
            lines.append(header)
        for name in sorted(aliases):
            alias = aliases[name]
            if alias.enabled:
                lines.append(self.render_alias(name, alias))
        footer = self.render_footer()
        if footer:
            lines.append(footer)
        return "\n".join(lines)


def get_renderer(shell: str) -> ShellRenderer:
    """Return the concrete renderer for *shell*.

    Args:
        shell: One of the :data:`SUPPORTED_SHELLS` identifiers.

    Returns:
        A :class:`ShellRenderer` instance.

    Raises:
        ValueError: If *shell* is not supported.
    """
    shell = shell.lower().strip()
    if shell == "bash":
        from qwik.shells.bash import BashRenderer

        return BashRenderer()
    if shell == "zsh":
        from qwik.shells.zsh import ZshRenderer

        return ZshRenderer()
    if shell == "fish":
        from qwik.shells.fish import FishRenderer

        return FishRenderer()
    if shell == "pwsh":
        from qwik.shells.pwsh import PwshRenderer

        return PwshRenderer()
    if shell == "cmd":
        from qwik.shells.cmd import CmdRenderer

        return CmdRenderer()
    raise ValueError(f"Unsupported shell: {shell}. Choose from {SUPPORTED_SHELLS}.")
