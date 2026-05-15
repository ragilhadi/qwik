"""``qwik add`` — create a new alias."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import typer
from rich.console import Console

from qwik.core.conflicts import ConflictChecker
from qwik.core.models import Alias
from qwik.core.store import get_store
from qwik.ui.prompts import (
    print_error,
    print_info,
    print_success,
    print_warning,
    prompt_confirm,
    prompt_text,
)

__all__ = ["add_command"]


def add_command(
    name: Optional[str] = typer.Argument(None, help="Alias name."),
    command: list[str] = typer.Argument(None, help="Command the alias expands to."),
    tag: Optional[str] = typer.Option(
        None, "--tag", "-t", help="Comma-separated tags."
    ),
    description: Optional[str] = typer.Option(
        None, "--description", "-d", help="Optional description."
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite if alias already exists."
    ),
    global_install: bool = typer.Option(
        False, "--global", "-g", help="(Reserved) install for all users."
    ),
) -> None:
    """Create a new alias.

    When *name* or *command* are omitted, the command runs interactively.
    """
    del global_install  # reserved for future use
    store = get_store()
    store_data = store.load()
    console = Console()

    # Interactive mode if name missing
    if name is None:
        name = prompt_text("? Alias name", console=console, allow_empty=False)
    if not command:
        cmd_input = prompt_text("? Command", console=console, allow_empty=False)
        command = [cmd_input]

    full_command = " ".join(command)

    # Conflict checks
    checker = ConflictChecker(store_data)
    result = checker.check(name)

    if not result.valid_syntax:
        print_error(
            result.name, suggestion="Names must match ^[A-Za-z_][A-Za-z0-9_-]*$"
        )
        raise typer.Exit(1)

    if result.existing_alias and not force:
        print_error(
            f'Alias "{name}" already exists.',
            suggestion=f"qwik edit {name}  to change the command\n"
            f"qwik rm {name}     to remove it\n"
            f"--force            to overwrite",
        )
        raise typer.Exit(1)

    if result.is_builtin and not force:
        print_error(
            f'"{name}" is a shell builtin. Shadowing it can break your shell.',
            suggestion="Use --force only if you know what you're doing.",
        )
        raise typer.Exit(1)

    if result.needs_warning:
        print_warning(
            f'"{name}" shadows {result.path_location}.',
            console=console,
        )
        if not prompt_confirm("Continue?", default=False, console=console):
            raise typer.Exit(0)

    alias = Alias(
        command=full_command,
        tag=tag or "",
        description=description or "",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    try:
        store_data.add(name, alias, force=force)
    except KeyError as exc:
        print_error(str(exc))
        raise typer.Exit(1)

    store.save_with_backup(store_data)
    print_success(f'Added "{name}" → {full_command!r}', console=console)
    print_info("Run `source <rc>` or open a new terminal to use it.", console=console)
