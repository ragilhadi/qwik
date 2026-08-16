"""``qwik pick`` — interactive fuzzy picker (also bare ``qwik``)."""

from __future__ import annotations

import subprocess
import sys

import typer

from qwik.core.store import get_store
from qwik.core.substitute import expand
from qwik.ui.picker import run_picker
from qwik.ui.prompts import print_error, print_success
from qwik.ui.theme import get_console

__all__ = ["pick_command"]


def pick_command() -> None:
    """Open the interactive fuzzy picker; selecting an alias runs it."""
    store = get_store()
    data = store.load()
    console = get_console()

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
    if alias is None and name in data.overlay_aliases:
        alias = data.overlay_aliases[name]
        data.add(name, alias)
        store.save_with_backup(data)
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

    # See qwik/commands/run.py for why this goes to stderr and is skipped
    # when stdout isn't a TTY: the banner must never land in the child
    # command's own output stream.
    if sys.stdout.isatty():
        print_success(
            f'Running "{name}" → {expanded!r}', console=get_console(stderr=True)
        )
    returncode = 1
    try:
        completed = subprocess.run(expanded, shell=True)
        returncode = completed.returncode
    except KeyboardInterrupt:
        # Child received SIGINT (e.g. user hit Ctrl+C on a long-running command).
        returncode = 130
    finally:
        try:
            store.bump_usage(name)
        except (OSError, RuntimeError):
            # best-effort usage tracking; never mask the command's exit code
            pass

    raise typer.Exit(returncode)
