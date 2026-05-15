"""``qwik tag`` / ``qwik untag`` — manage alias tags."""

from __future__ import annotations

from datetime import datetime, timezone

import typer
from rich.console import Console

from qwik.core.store import get_store
from qwik.ui.prompts import print_error, print_success

__all__ = ["tag_command", "untag_command"]


def tag_command(
    name: str = typer.Argument(..., help="Alias name."),
    tag: str = typer.Argument(..., help="Tag to add."),
) -> None:
    """Attach a tag to an alias."""
    store = get_store()
    data = store.load()
    console = Console()

    alias = data.get(name)
    if alias is None:
        print_error(f'Alias "{name}" does not exist.', console=console)
        raise typer.Exit(1)

    if tag not in alias.tag:
        alias.tag.append(tag)
        alias.updated_at = datetime.now(timezone.utc)
        store.save_with_backup(data)

    print_success(f'Tagged "{name}" with "{tag}".', console=console)


def untag_command(
    name: str = typer.Argument(..., help="Alias name."),
    tag: str = typer.Argument(..., help="Tag to remove."),
) -> None:
    """Remove a tag from an alias."""
    store = get_store()
    data = store.load()
    console = Console()

    alias = data.get(name)
    if alias is None:
        print_error(f'Alias "{name}" does not exist.', console=console)
        raise typer.Exit(1)

    if tag in alias.tag:
        alias.tag.remove(tag)
        alias.updated_at = datetime.now(timezone.utc)
        store.save_with_backup(data)

    print_success(f'Removed tag "{tag}" from "{name}".', console=console)
