"""Rich theme tokens and console helpers."""

from __future__ import annotations

import os
from typing import Any

from rich.console import Console
from rich.style import Style
from rich.theme import Theme

__all__ = [
    "get_console",
    "THEME",
    "style",
]

_NO_COLOR_OVERRIDE: bool = False


def _no_color_active() -> bool:
    """True if color output is disabled via flag, env, or platform."""
    if _NO_COLOR_OVERRIDE:
        return True
    return os.environ.get("NO_COLOR") is not None


THEME = Theme(
    {
        "qwik.success": "bold green",
        "qwik.warning": "bold yellow",
        "qwik.error": "bold red",
        "qwik.info": "dim cyan",
        "qwik.dim": "dim",
        "qwik.highlight": "bold magenta",
    }
)


def get_console(*, no_color: bool = False, **kwargs: Any) -> Console:
    """Return a :class:`~rich.console.Console` with the ``qwik`` theme.

    Args:
        no_color: If ``True``, force plain text output regardless of
            ``NO_COLOR`` or TTY state.
        **kwargs: Additional keyword arguments forwarded to
            :class:`~rich.console.Console`.

    Returns:
        A configured Rich console.
    """
    color_system = None if (no_color or _no_color_active()) else "auto"
    return Console(theme=THEME, color_system=color_system, **kwargs)


def style(name: str) -> Style:
    """Look up a style token by name.

    Args:
        name: Theme key such as ``qwik.success``.

    Returns:
        The corresponding :class:`~rich.style.Style`.
    """
    return THEME.styles[name]
