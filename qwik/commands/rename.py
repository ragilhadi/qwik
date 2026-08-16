"""``qwik rename`` — rename an alias."""

from __future__ import annotations

from typing import Optional

import typer

from qwik.core.conflicts import ConflictChecker
from qwik.core.shell_detect import detect_shell as _detect_shell
from qwik.core.store import get_store
from qwik.ui.prompts import print_error, print_success
from qwik.ui.theme import get_console

__all__ = ["rename_command"]


def rename_command(
    old: str = typer.Argument(..., help="Current alias name."),
    new: str = typer.Argument(..., help="New alias name."),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite if target exists."
    ),
    shell: Optional[str] = typer.Option(
        None, "--shell", hidden=True, help="Override shell detection for conflict checks."
    ),
) -> None:
    """Rename an alias, checking for conflicts."""
    store = get_store()
    data = store.load()
    console = get_console()

    if old in data.overlay_aliases and old not in data.aliases:
        print_error(
            f"'{old}' is an overlay alias (read-only). "
            f"Copy it first: qwik overlay copy --name {old}",
            console=console,
        )
        raise typer.Exit(1)

    if old not in data.aliases:
        print_error(f'Alias "{old}" does not exist.', console=console)
        raise typer.Exit(1)

    checker = ConflictChecker(data)
    active_shell = shell or _detect_shell()
    result = checker.check(new, shell=active_shell)

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

    try:
        with store.mutate() as fresh_data:
            fresh_data.rename(old, new)
    except KeyError as exc:
        print_error(str(exc), console=console)
        raise typer.Exit(1)
    print_success(f'Renamed "{old}" → "{new}".', console=console)
