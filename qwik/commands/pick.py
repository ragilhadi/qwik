"""``qwik pick`` — interactive fuzzy picker (also bare ``qwik``)."""

from __future__ import annotations

import subprocess

import typer
from rich.console import Console

from qwik.core.store import get_store
from qwik.core.substitute import expand
from qwik.ui.picker import run_picker
from qwik.ui.prompts import print_error, print_success

__all__ = ["pick_command"]


def pick_command() -> None:
    """Open the interactive fuzzy picker; selecting an alias runs it."""
    store = get_store()
    data = store.load()
    console = Console()

    selected = run_picker(data)
    if selected is None:
        raise typer.Exit(0)

    # Handle special actions from picker keybindings
    if selected.startswith("__edit__:"):
        name = selected.split(":", 1)[1]
        # Delegate to edit command by re-invoking CLI
        from typer.testing import CliRunner
        from qwik.cli import app

        result = CliRunner().invoke(app, ["edit", name])
        console.print(result.output)
        raise typer.Exit(result.exit_code)

    if selected.startswith("__delete__:"):
        name = selected.split(":", 1)[1]
        from typer.testing import CliRunner
        from qwik.cli import app

        result = CliRunner().invoke(app, ["rm", name])
        console.print(result.output)
        raise typer.Exit(result.exit_code)

    name = selected
    alias = data.get(name)
    if alias is None:
        print_error(f'Alias "{name}" disappeared.', console=console)
        raise typer.Exit(1)

    if not alias.enabled:
        print_error(f'Alias "{name}" is disabled.', console=console)
        raise typer.Exit(1)

    try:
        expanded = expand(alias.command, [])
    except ValueError as exc:
        print_error(str(exc), console=console)
        raise typer.Exit(1)

    print_success(f'Running "{name}" → {expanded!r}', console=console)
    returncode = 1
    try:
        result = subprocess.run(expanded, shell=True)
        returncode = result.returncode
    except KeyboardInterrupt:
        # Child received SIGINT (e.g. user hit Ctrl+C on a long-running command).
        returncode = 130
    finally:
        alias.bump_usage()
        store.save_with_backup(data)

    raise typer.Exit(returncode)
