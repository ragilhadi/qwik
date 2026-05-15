"""``qwik show`` — detailed view of one alias."""

from __future__ import annotations

import typer

from qwik.core.store import get_store
from qwik.ui.prompts import print_error
from qwik.ui.tables import render_alias_detail
from qwik.ui.theme import get_console

__all__ = ["show_command"]


def show_command(
    name: str = typer.Argument(..., help="Alias name to inspect."),
) -> None:
    """Display detailed metadata for a single alias."""
    store = get_store()
    data = store.load()
    console = get_console()

    alias = data.get(name)
    if alias is None:
        print_error(f'Alias "{name}" does not exist.', console=console)
        raise typer.Exit(1)

    table = render_alias_detail(name, alias)
    console.print(table)
