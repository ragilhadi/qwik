"""Abstract base class and per-shell renderers for shell hook generation."""

from __future__ import annotations

import functools
import importlib.metadata
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from pathlib import Path
    from qwik.core.models import Alias

__all__ = [
    "ShellRenderer",
    "get_renderer",
    "supported_shells",
    "SUPPORTED_SHELLS",
]

_ENTRY_POINT_GROUP = "qwik.shell_renderers"


@functools.cache
def supported_shells() -> tuple[str, ...]:
    """Return all registered shell identifiers, sorted.

    Discovers shells via the ``qwik.shell_renderers`` entry-point group.
    Entry-point discovery walks installed-distribution metadata on disk,
    so the result is cached: at most one scan per process, and only when
    something actually needs it (not at import time — most invocations,
    like ``qwik add``, never call this at all).
    """
    eps = importlib.metadata.entry_points(group=_ENTRY_POINT_GROUP)
    return tuple(sorted(ep.name for ep in eps))


@functools.cache
def _renderer_registry() -> dict[str, type]:
    """Return ``{shell_name: renderer_class}``, loaded and cached once."""
    return {
        ep.name: ep.load()
        for ep in importlib.metadata.entry_points(group=_ENTRY_POINT_GROUP)
    }


def __getattr__(name: str) -> Any:
    """Compute ``SUPPORTED_SHELLS`` lazily on first access (PEP 562).

    Kept as a module attribute for backward compatibility with any
    ``from qwik.shells.base import SUPPORTED_SHELLS`` import, but no
    longer computed eagerly at import time.
    """
    if name == "SUPPORTED_SHELLS":
        return supported_shells()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
        """Return an optional header emitted before alias definitions."""
        return ""

    def render_footer(self) -> str:
        """Return an optional footer emitted after alias definitions."""
        return ""

    def rc_path(self) -> "Path | None":
        """Return the RC file path for this shell, or ``None`` if unsupported."""
        return None

    def install_hook_line(self) -> str | None:
        """Return the hook line to append to the RC file, or ``None``."""
        return None

    def render_all(self, aliases: dict[str, "Alias"]) -> str:
        """Render a complete hook snippet for the given alias map.

        Only **enabled** aliases are included.  Output is sorted by name
        for stable generation.
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

    Discovers renderers via the ``qwik.shell_renderers`` entry-point
    group, cached after the first call (see :func:`_renderer_registry`)
    rather than re-scanning entry points on every call.

    Raises:
        ValueError: If *shell* is not supported.
    """
    shell = shell.lower().strip()
    cls = _renderer_registry().get(shell)
    if cls is None:
        raise ValueError(
            f"Unsupported shell: {shell}. Choose from {supported_shells()}."
        )
    return cast("ShellRenderer", cls())
