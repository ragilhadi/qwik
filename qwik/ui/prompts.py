"""Reusable interactive prompts using Rich."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from qwik.ui.theme import get_console

if TYPE_CHECKING:
    from rich.console import Console

__all__ = [
    "prompt_confirm",
    "prompt_text",
    "print_error",
    "print_success",
    "print_warning",
    "print_info",
]


def _get_console(console: "Console" | None) -> "Console":
    """Return the provided console or the default one."""
    return console if console is not None else get_console()


def prompt_confirm(
    message: str,
    *,
    default: bool = False,
    console: "Console" | None = None,
) -> bool:
    """Ask the user a yes/no question.

    Args:
        message: The prompt text.
        default: The default answer when the user presses Enter.
        console: Optional Rich console.

    Returns:
        ``True`` if the user confirmed, otherwise ``False``.
    """
    con = _get_console(console)
    return Confirm.ask(message, default=default, console=con)


def prompt_text(
    message: str,
    *,
    default: str = "",
    console: "Console" | None = None,
    allow_empty: bool = True,
) -> str:
    """Prompt for free-text input.

    Args:
        message: The prompt text.
        default: Default value if the user presses Enter without typing.
        console: Optional Rich console.
        allow_empty: If ``False``, reprompt until a non-empty string is given.

    Returns:
        The user's input (or *default*).
    """
    con = _get_console(console)
    while True:
        value = Prompt.ask(message, default=default, console=con)
        if value or allow_empty:
            return value
        con.print("[qwik.error]Input cannot be empty.[/qwik.error]")


def print_error(
    message: str, *, suggestion: str | None = None, console: "Console" | None = None
) -> None:
    """Render a red error panel with an optional suggestion line.

    Args:
        message: Primary error text.
        suggestion: Second line offering a fix or alternative.
        console: Optional Rich console.
    """
    con = _get_console(console)
    text = f"[qwik.error]✗ {message}[/qwik.error]"
    if suggestion:
        text += f"\n[qwik.dim]  → {suggestion}[/qwik.dim]"
    con.print(Panel(text, border_style="red"))


def print_success(message: str, *, console: "Console" | None = None) -> None:
    """Render a green success indicator.

    Args:
        message: Text to display after the checkmark.
        console: Optional Rich console.
    """
    con = _get_console(console)
    con.print(f"[qwik.success]✓ {message}[/qwik.success]")


def print_warning(message: str, *, console: "Console" | None = None) -> None:
    """Render a yellow warning indicator.

    Args:
        message: Text to display after the warning symbol.
        console: Optional Rich console.
    """
    con = _get_console(console)
    con.print(f"[qwik.warning]⚠ {message}[/qwik.warning]")


def print_info(message: str, *, console: "Console" | None = None) -> None:
    """Render a dim informational indicator.

    Args:
        message: Text to display after the info symbol.
        console: Optional Rich console.
    """
    con = _get_console(console)
    con.print(f"[qwik.info]ℹ {message}[/qwik.info]")
