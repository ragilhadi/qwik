"""``qwik enable`` / ``qwik disable`` — toggle alias state."""

from __future__ import annotations

from datetime import datetime, timezone

import typer

from qwik.core.store import get_store
from qwik.ui.prompts import print_error, print_success
from qwik.ui.theme import get_console

__all__ = ["enable_command", "disable_command"]


def _toggle(name: str, enabled: bool) -> None:
    """Set the enabled flag for *name* and persist.

    Args:
        name: Alias identifier.
        enabled: Desired state.
    """
    store = get_store()
    console = get_console()

    with store.mutate() as data:
        alias = data.get(name)
        if alias is None:
            print_error(f'Alias "{name}" does not exist.', console=console)
            raise typer.Exit(1)

        alias.enabled = enabled
        alias.updated_at = datetime.now(timezone.utc)

    state = "enabled" if enabled else "disabled"
    print_success(f'"{name}" is now {state}.', console=console)


def enable_command(
    name: str = typer.Argument(..., help="Alias name to enable."),
) -> None:
    """Re-enable a previously disabled alias."""
    _toggle(name, True)


def disable_command(
    name: str = typer.Argument(..., help="Alias name to disable."),
) -> None:
    """Temporarily disable an alias without deleting it."""
    _toggle(name, False)
