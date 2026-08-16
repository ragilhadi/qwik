"""``qwik pick`` — interactive fuzzy picker (also bare ``qwik``)."""

from __future__ import annotations

import subprocess
import sys

import typer

from qwik.commands.edit import edit_alias
from qwik.commands.remove import remove_alias
from qwik.core.shell_detect import detect_shell
from qwik.core.shell_exec import build_invocation
from qwik.core.store import get_store
from qwik.core.substitute import expand
from qwik.ui.picker import PickerAction, run_picker
from qwik.ui.prompts import print_error, print_success
from qwik.ui.theme import get_console

__all__ = ["pick_command"]


def pick_command() -> None:
    """Open the interactive fuzzy picker; selecting an alias runs it."""
    store = get_store()
    data = store.load()
    console = get_console()

    result = run_picker(data)
    if result is None:
        raise typer.Exit(0)

    if result.action is PickerAction.EDIT:
        # Call the command's own logic directly rather than re-entering
        # the CLI through a test harness — typer.testing.CliRunner
        # replaces stdin with an empty stream and buffers stdout, so a
        # confirmation prompt inside it can never reach the real
        # terminal. This runs with the real TTY, exactly like `qwik edit`
        # invoked directly would.
        edit_alias(result.name)
        raise typer.Exit(0)

    if result.action is PickerAction.DELETE:
        remove_alias(result.name, yes=False)
        raise typer.Exit(0)

    name = result.name
    alias = data.get(name)
    if alias is None and name in data.overlay_aliases:
        alias = data.overlay_aliases[name]
        with store.mutate() as fresh_data:
            if name not in fresh_data.aliases:
                fresh_data.add(name, alias)
    if alias is None:
        print_error(f'Alias "{name}" disappeared.', console=console)
        raise typer.Exit(1)

    if not alias.enabled:
        print_error(f'Alias "{name}" is disabled.', console=console)
        raise typer.Exit(1)

    active_shell = detect_shell()
    try:
        expanded = expand(alias.command, [], shell=active_shell)
    except ValueError as exc:
        print_error(str(exc), console=console)
        raise typer.Exit(1) from exc

    # See qwik/commands/run.py for why this goes to stderr and is skipped
    # when stdout isn't a TTY: the banner must never land in the child
    # command's own output stream.
    if sys.stdout.isatty():
        print_success(f'Running "{name}" → {expanded!r}', console=get_console(stderr=True))
    returncode = 1
    try:
        cmd, use_shell = build_invocation(expanded, active_shell)
        completed = subprocess.run(cmd, shell=use_shell, check=False)
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
