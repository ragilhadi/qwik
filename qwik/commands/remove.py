"""``qwik rm`` — delete an alias."""

from __future__ import annotations


import typer
from rich.console import Console

from qwik.core.store import get_store
from qwik.ui.prompts import print_error, print_success, prompt_confirm

__all__ = ["remove_command"]


def remove_command(
    name: str = typer.Argument(..., help="Alias name to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Delete an alias (with confirmation unless ``--yes``)."""
    store = get_store()
    data = store.load()
    console = Console()

    if name not in data.aliases:
        print_error(f'Alias "{name}" does not exist.', console=console)
        raise typer.Exit(1)

    if not yes:
        alias = data.aliases[name]
        console.print(f'Remove "{name}" → {alias.command!r}?')
        if not prompt_confirm("Confirm", default=False, console=console):
            raise typer.Exit(0)

    data.remove(name)
    store.save_with_backup(data)
    print_success(f'Removed "{name}".', console=console)
