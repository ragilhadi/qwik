"""Rich theme tokens and console helpers."""

from __future__ import annotations

import os
from typing import Any, Literal

from rich.console import Console
from rich.style import Style
from rich.theme import Theme

__all__ = [
    "get_console",
    "THEME",
    "style",
]


def _no_color_active() -> bool:
    """True if color output is disabled via flag, env, or platform.

    The ``--no-color`` flag is carried on the current Click/Typer
    context's ``obj`` (set once by the top-level callback) rather than
    a mutable module-level global: a global would need to be
    reassigned on every invocation to avoid leaking a prior process's
    (or, in tests, a prior CliRunner.invoke's) value into one that never
    passed the flag at all.
    """
    if os.environ.get("NO_COLOR") is not None:
        return True
    try:
        from typer._click.globals import get_current_context

        ctx = get_current_context(silent=True)
    except Exception:
        ctx = None
    obj = getattr(ctx, "obj", None)
    return isinstance(obj, dict) and bool(obj.get("no_color"))


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
    color_system: Literal["auto", "standard", "256", "truecolor", "windows"] | None = (
        None if (no_color or _no_color_active()) else "auto"
    )
    return Console(theme=THEME, color_system=color_system, **kwargs)


def style(name: str) -> Style:
    """Look up a style token by name.

    Args:
        name: Theme key such as ``qwik.success``.

    Returns:
        The corresponding :class:`~rich.style.Style`.
    """
    return THEME.styles[name]
