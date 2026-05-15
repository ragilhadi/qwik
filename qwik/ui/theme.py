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

# Respect NO_COLOR environment variable per PRD §7.
_FORCE_COLOR: bool | None = None if os.environ.get("NO_COLOR") is None else False

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
    color_system = None if (_FORCE_COLOR is False or no_color) else "auto"
    return Console(theme=THEME, color_system=color_system, **kwargs)


def style(name: str) -> Style:
    """Look up a style token by name.

    Args:
        name: Theme key such as ``qwik.success``.

    Returns:
        The corresponding :class:`~rich.style.Style`.
    """
    return THEME.styles[name]
