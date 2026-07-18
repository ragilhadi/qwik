"""``qwik run`` / ``qwik -r`` — execute an alias via subprocess.

All aliases are executed under ``shell=True`` because alias commands are
shell snippets that may legitimately use pipes, redirects, and compound
operators. Runtime arguments are pre-quoted by :mod:`qwik.core.substitute`
to prevent injection.
"""

from __future__ import annotations

import subprocess

import typer

from qwik.core.store import get_store
from qwik.core.substitute import expand
from qwik.ui.prompts import print_error, print_success
from qwik.ui.theme import get_console

__all__ = ["run_command"]


def run_command(
    name: str = typer.Argument(..., help="Alias name to run."),
    args: list[str] = typer.Argument(None, help="Arguments to pass to the alias."),
) -> None:
    """Execute an alias via subprocess (works without shell hooks)."""
    store = get_store()
    data = store.load()
    console = get_console()

    alias = data.get(name)
    if alias is None:
        print_error(f'Alias "{name}" does not exist.', console=console)
        raise typer.Exit(1)

    if not alias.enabled:
        print_error(f'Alias "{name}" is disabled. Run `qwik enable {name}` first.')
        raise typer.Exit(1)

    try:
        expanded = expand(alias.command, args or [])
    except ValueError as exc:
        print_error(str(exc), console=console)
        raise typer.Exit(1)

    print_success(f'Running "{name}" → {expanded!r}', console=console)
    returncode = 1
    try:
        result = subprocess.run(expanded, shell=True)
        returncode = result.returncode
    except KeyboardInterrupt:
        # Child received SIGINT (e.g. user hit Ctrl+C on docker stats).
        returncode = 130
    finally:
        try:
            store.bump_usage(name)
        except OSError:
            # best-effort usage tracking; never mask the command's exit code
            pass

    raise typer.Exit(returncode)
