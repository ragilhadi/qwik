"""``qwik run`` / ``qwik -r`` — execute an alias via subprocess."""

from __future__ import annotations

import subprocess

import typer
from rich.console import Console

from qwik.core.store import get_store
from qwik.core.substitute import expand
from qwik.ui.prompts import print_error, print_success

__all__ = ["run_command"]


def _has_shell_metacharacters(cmd: str) -> bool:
    """Detect characters that require ``shell=True``.

    Args:
        cmd: The expanded command string.

    Returns:
        ``True`` if *cmd* contains characters like ``|``, ``>``, ``<``,
        ``;``, ``&``, ``$``, backticks, ``~``, ``*``, ``(``, ``)``,
        or compound operators ``&&`` / ``||``.
    """
    if "&&" in cmd or "||" in cmd:
        return True
    return any(c in cmd for c in r"|<>&$`~*()")


def run_command(
    name: str = typer.Argument(..., help="Alias name to run."),
    args: list[str] = typer.Argument(None, help="Arguments to pass to the alias."),
) -> None:
    """Execute an alias via subprocess (works without shell hooks)."""
    store = get_store()
    data = store.load()
    console = Console()

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
        alias.bump_usage()
        store.save_with_backup(data)

    raise typer.Exit(returncode)
