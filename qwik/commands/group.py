"""``qwik group`` / ``qwik ungroup`` — manage the canonical group of an alias."""

from __future__ import annotations

from datetime import datetime, timezone

import typer

from qwik.core.models import validate_alias_name
from qwik.core.store import get_store
from qwik.ui.prompts import print_error, print_info, print_success
from qwik.ui.theme import get_console

__all__ = ["group_command", "ungroup_command"]


def group_command(
    name: str = typer.Argument(..., help="Alias name."),
    group: str = typer.Argument(..., help="Group to assign."),
) -> None:
    """Assign the canonical group of an alias."""
    store = get_store()
    console = get_console()

    group = group.strip()
    try:
        validated = validate_alias_name(group)
    except ValueError as exc:
        print_error(
            f'Invalid group "{group}": {exc}',
            console=console,
        )
        raise typer.Exit(1)

    with store.mutate() as data:
        alias = data.get(name)
        if alias is None:
            print_error(f'Alias "{name}" does not exist.', console=console)
            raise typer.Exit(1)

        if alias.group == validated:
            print_info(f'"{name}" already in group "{validated}".', console=console)
            raise typer.Exit(0)

        alias.group = validated
        alias.updated_at = datetime.now(timezone.utc)

    print_success(f'Grouped "{name}" under "{validated}".', console=console)


def ungroup_command(
    name: str = typer.Argument(..., help="Alias name."),
) -> None:
    """Remove the canonical group from an alias."""
    store = get_store()
    console = get_console()

    with store.mutate() as data:
        alias = data.get(name)
        if alias is None:
            print_error(f'Alias "{name}" does not exist.', console=console)
            raise typer.Exit(1)

        if alias.group is None:
            print_info(f'"{name}" has no group.', console=console)
            raise typer.Exit(0)

        alias.group = None
        alias.updated_at = datetime.now(timezone.utc)

    print_success(f'Removed group from "{name}".', console=console)
