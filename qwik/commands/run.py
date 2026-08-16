"""``qwik run`` / ``qwik -r`` — execute an alias via subprocess.

All aliases are executed under ``shell=True`` because alias commands are
shell snippets that may legitimately use pipes, redirects, and compound
operators. Runtime arguments are pre-quoted by :mod:`qwik.core.substitute`
to prevent injection.
"""

from __future__ import annotations

import subprocess
import sys

import typer

from qwik.core.shell_detect import detect_shell
from qwik.core.shell_exec import build_invocation
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
    if alias is None and name in data.overlay_aliases:
        alias = data.overlay_aliases[name]
        with store.mutate() as fresh_data:
            if name not in fresh_data.aliases:
                fresh_data.add(name, alias)
    if alias is None:
        print_error(f'Alias "{name}" does not exist.', console=console)
        raise typer.Exit(1)

    if not alias.enabled:
        print_error(f'Alias "{name}" is disabled. Run `qwik enable {name}` first.')
        raise typer.Exit(1)

    active_shell = detect_shell()
    try:
        expanded = expand(alias.command, args or [], shell=active_shell)
    except ValueError as exc:
        print_error(str(exc), console=console)
        raise typer.Exit(1) from exc

    # The banner must never touch stdout: `qwik run` is meant to be
    # composable in pipes and `$(...)` captures, and a decorated status
    # line interleaved with the child's own output would corrupt both. It
    # is also only useful to a human watching the terminal, so it is
    # skipped entirely when stdout isn't a TTY (e.g. piped or captured).
    if sys.stdout.isatty():
        print_success(f'Running "{name}" → {expanded!r}', console=get_console(stderr=True))
    returncode = 1
    try:
        cmd, use_shell = build_invocation(expanded, active_shell)
        result = subprocess.run(cmd, shell=use_shell, check=False)
        returncode = result.returncode
    except KeyboardInterrupt:
        # Child received SIGINT (e.g. user hit Ctrl+C on docker stats).
        returncode = 130
    finally:
        try:
            store.bump_usage(name)
        except (OSError, RuntimeError):
            # best-effort usage tracking; never mask the command's exit code
            pass

    raise typer.Exit(returncode)
