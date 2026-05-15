"""``qwik rename`` — rename an alias."""

from __future__ import annotations

import typer
from rich.console import Console

from qwik.core.conflicts import ConflictChecker
from qwik.core.store import get_store
from qwik.ui.prompts import print_error, print_success

__all__ = ["rename_command"]


def rename_command(
    old: str = typer.Argument(..., help="Current alias name."),
    new: str = typer.Argument(..., help="New alias name."),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite if target exists."
    ),
) -> None:
    """Rename an alias, checking for conflicts."""
    store = get_store()
    data = store.load()
    console = Console()

    if old not in data.aliases:
        print_error(f'Alias "{old}" does not exist.', console=console)
        raise typer.Exit(1)

    checker = ConflictChecker(data)
    result = checker.check(new)

    if not result.valid_syntax:
        print_error(new, suggestion="Names must match ^[A-Za-z_][A-Za-z0-9_-]*$")
        raise typer.Exit(1)

    if result.existing_alias and not force:
        print_error(
            f'Alias "{new}" already exists.', suggestion="Use --force to overwrite."
        )
        raise typer.Exit(1)

    if result.is_builtin and not force:
        print_error(
            f'"{new}" is a shell builtin.', suggestion="Use --force to override."
        )
        raise typer.Exit(1)

    data.rename(old, new)
    store.save_with_backup(data)
    print_success(f'Renamed "{old}" → "{new}".', console=console)
