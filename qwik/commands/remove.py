"""``qwik rm`` — delete an alias."""

from __future__ import annotations


import typer

from qwik.core.store import get_store
from qwik.ui.prompts import print_error, print_success, prompt_confirm
from qwik.ui.theme import get_console

__all__ = ["remove_command", "remove_alias"]


def remove_command(
    name: str = typer.Argument(..., help="Alias name to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Delete an alias (with confirmation unless ``--yes``)."""
    remove_alias(name, yes=yes)


def remove_alias(name: str, *, yes: bool) -> None:
    """Delete *name*; the logic behind ``remove_command``.

    A plain function taking real values rather than ``typer.Argument``/
    ``typer.Option`` defaults, so callers other than Click — the
    picker's Ctrl+D binding — can invoke it directly instead of going
    through a CLI-testing shim.

    Args:
        name: Alias identifier to delete.
        yes: If ``True``, skip the confirmation prompt.
    """
    store = get_store()
    data = store.load()
    console = get_console()

    if name in data.overlay_aliases and name not in data.aliases:
        print_error(
            f"'{name}' is an overlay alias (read-only). "
            f"Copy it first: qwik overlay copy --name {name}",
            console=console,
        )
        raise typer.Exit(1)

    if name not in data.aliases:
        print_error(f'Alias "{name}" does not exist.', console=console)
        raise typer.Exit(1)

    if not yes:
        alias = data.aliases[name]
        console.print(f'Remove "{name}" → {alias.command!r}?')
        if not prompt_confirm("Confirm", default=False, console=console):
            raise typer.Exit(0)

    try:
        with store.mutate() as fresh_data:
            fresh_data.remove(name)
    except KeyError as exc:
        print_error(str(exc), console=console)
        raise typer.Exit(1)
    print_success(f'Removed "{name}".', console=console)
