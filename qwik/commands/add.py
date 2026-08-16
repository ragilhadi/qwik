"""``qwik add`` — create a new alias."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

import typer

from qwik.core.conflicts import ConflictChecker
from qwik.core.models import Alias, validate_alias_name
from qwik.core.shell_detect import detect_shell as _detect_shell
from qwik.core.store import get_store
from qwik.core.substitute import has_placeholders
from qwik.ui.prompts import (
    print_error,
    print_info,
    print_success,
    print_warning,
    prompt_confirm,
    prompt_text,
)
from qwik.ui.theme import get_console

__all__ = ["add_command"]

_CMD_VAR_RE: re.Pattern[str] = re.compile(r"%[A-Za-z_][A-Za-z0-9_]*%")
_PWSH_VAR_RE: re.Pattern[str] = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*")


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
    group: Optional[str] = typer.Option(
        None, "--group", "-g", help="Primary group for the alias."
    ),
    shell: Optional[str] = typer.Option(
        None, "--shell", hidden=True, help="Override shell detection for conflict checks."
    ),
) -> None:
    """Create a new alias.

    When *name* or *command* are omitted, the command runs interactively.
    """
    store = get_store()
    store_data = store.load()
    console = get_console()

    # Interactive mode if name missing
    if name is None:
        name = prompt_text("? Alias name", console=console, allow_empty=False)
    if not command:
        cmd_input = prompt_text("? Command", console=console, allow_empty=False)
        command = [cmd_input]

    full_command = " ".join(command)

    from qwik.core.substitute import validate_placeholders_static

    try:
        validate_placeholders_static(full_command)
    except ValueError as exc:
        print_error(str(exc), console=console)
        raise typer.Exit(1)

    # Conflict checks
    checker = ConflictChecker(store_data)
    active_shell = shell or _detect_shell()
    result = checker.check(name, shell=active_shell)

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

    if result.needs_warning and not force:
        print_warning(
            f'"{name}" shadows {result.path_location}.',
            console=console,
        )
        if not prompt_confirm("Continue?", default=False, console=console):
            raise typer.Exit(0)

    if group is not None:
        try:
            validate_alias_name(group)
        except ValueError as exc:
            print_error(f'Invalid group "{group}": {exc}', console=console)
            raise typer.Exit(1)

    if active_shell is not None:
        if active_shell == "cmd" and has_placeholders(full_command):
            print_warning(
                "cmd/doskey does not support parameterized aliases; "
                f'"{name}" will be omitted from cmd hooks. '
                "Use bash/zsh/fish/pwsh for templates, or run "
                f"`qwik run {name} ...` directly.",
                console=console,
            )
        var_match: re.Match[str] | None = None
        if active_shell == "cmd":
            var_match = _CMD_VAR_RE.search(full_command)
        elif active_shell == "pwsh":
            var_match = _PWSH_VAR_RE.search(full_command)
        if var_match is not None:
            example = var_match.group(0)
            print_warning(
                f"Command contains {example} which will be expanded by "
                f"{active_shell} at run time. If you want a literal {example}, "
                "escape it per your shell's rules.",
                console=console,
            )

    alias = Alias(
        command=full_command,
        tag=tag or [],  # type: ignore[arg-type]
        group=group,
        description=description or "",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    try:
        with store.mutate() as fresh_data:
            fresh_data.add(name, alias, force=force)
    except KeyError as exc:
        print_error(str(exc))
        raise typer.Exit(1)

    print_success(f'Added "{name}" → {full_command!r}', console=console)
    print_info("Run `source <rc>` or open a new terminal to use it.", console=console)
