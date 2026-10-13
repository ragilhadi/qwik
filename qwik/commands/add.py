"""``qwik add`` — create a new alias."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import typer
from rich.console import Console

from qwik.core.conflicts import ConflictChecker, ConflictResult
from qwik.core.models import Alias, AliasStore, validate_alias_name
from qwik.core.platform import validate_platform, variant_key
from qwik.core.shell_detect import detect_shell as _detect_shell
from qwik.core.store import Store, get_store
from qwik.core.substitute import (
    has_placeholders,
    placeholder_arity,
    placeholders_compatible,
    validate_placeholders_static,
)
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

_CMD_VAR_RE: re.Pattern[str] = re.compile(r"%[A-Za-z_]\w*%")
_PWSH_VAR_RE: re.Pattern[str] = re.compile(r"\$[A-Za-z_]\w*")


def _enforce_conflict_gates(
    result: ConflictResult, name: str, force: bool, group: str | None, console: Console
) -> None:
    """Abort with a typer.Exit for any unforced conflict or an invalid group."""
    if not result.valid_syntax:
        print_error(result.name, suggestion="Names must match ^[A-Za-z_][A-Za-z0-9_-]*$")
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

    _validate_group(group, console)


def _validate_group(group: str | None, console: Console) -> None:
    if group is not None:
        try:
            validate_alias_name(group)
        except ValueError as exc:
            print_error(f'Invalid group "{group}": {exc}', console=console)
            raise typer.Exit(1) from exc


def _warn_shell_compatibility(
    active_shell: str, name: str, full_command: str, console: Console
) -> None:
    """Warn about cmd/doskey gaps and shell variable placeholders."""
    if active_shell == "cmd" and has_placeholders(full_command):
        print_warning(
            "cmd/doskey does not support parameterized aliases; "
            f'"{name}" will be omitted from cmd hooks. '
            "Use bash/zsh/fish/pwsh for templates, or run "
            f"`qwik run {name} ...` directly.",
            console=console,
        )
    var = _find_shell_var(active_shell, full_command)
    if var is not None:
        print_warning(
            f"Command contains {var} which will be expanded by "
            f"{active_shell} at run time. If you want a literal {var}, "
            "escape it per your shell's rules.",
            console=console,
        )


def _find_shell_var(active_shell: str, full_command: str) -> str | None:
    var_match: re.Match[str] | None = None
    if active_shell == "cmd":
        var_match = _CMD_VAR_RE.search(full_command)
    elif active_shell == "pwsh":
        var_match = _PWSH_VAR_RE.search(full_command)
    return var_match.group(0) if var_match is not None else None


def add_command(
    name: str | None = typer.Argument(None, help="Alias name."),
    command: list[str] = typer.Argument(None, help="Command the alias expands to."),
    tag: str | None = typer.Option(None, "--tag", "-t", help="Comma-separated tags."),
    description: str | None = typer.Option(
        None, "--description", "-d", help="Optional description."
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite if alias already exists."),
    group: str | None = typer.Option(None, "--group", "-g", help="Primary group for the alias."),
    platform: str | None = typer.Option(
        None,
        "--platform",
        "-p",
        help="Store the command as a platform-conditional variant "
        "(linux, macos, windows). On an existing alias this upserts only the "
        "variant; a new alias gets the command as both its base and variant.",
    ),
    shell: str | None = typer.Option(
        None, "--shell", hidden=True, help="Override shell detection for conflict checks."
    ),
) -> None:
    """Create a new alias.

    When *name* or *command* are omitted, the command runs interactively.
    With ``--platform``, the command is stored as a platform-conditional
    variant (``command_<platform>`` in the store) instead of only as the
    base ``command``.
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

    try:
        validate_placeholders_static(full_command)
    except ValueError as exc:
        print_error(str(exc), console=console)
        raise typer.Exit(1) from exc

    platform_key: str | None = None
    if platform is not None:
        try:
            platform_key = validate_platform(platform)
        except ValueError as exc:
            print_error(str(exc), console=console)
            raise typer.Exit(1) from exc

    checker = ConflictChecker(store_data)
    active_shell = shell or _detect_shell()

    if platform_key is None:
        _add_base_alias(
            checker,
            store,
            name,
            full_command,
            active_shell,
            tag,
            description,
            group,
            force,
            console,
        )
        return

    _add_platform_variant(
        checker,
        store,
        store_data,
        name,
        full_command,
        platform_key,
        active_shell,
        force,
        console,
    )


def _add_base_alias(
    checker: ConflictChecker,
    store: Store,
    name: str,
    full_command: str,
    active_shell: str | None,
    tag: str | None,
    description: str | None,
    group: str | None,
    force: bool,
    console: Console,
) -> None:
    """Create (or ``--force`` overwrite) a plain base alias."""
    result = checker.check(name, shell=active_shell)
    _enforce_conflict_gates(result, name, force, group, console)

    if active_shell is not None:
        _warn_shell_compatibility(active_shell, name, full_command, console)

    alias = Alias(
        command=full_command,
        tag=tag or [],  # type: ignore[arg-type]
        group=group,
        description=description or "",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    try:
        with store.mutate() as fresh_data:
            fresh_data.add(name, alias, force=force)
    except KeyError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from exc

    print_success(f'Added "{name}" → {full_command!r}', console=console)
    print_info("Run `source <rc>` or open a new terminal to use it.", console=console)


def _add_platform_variant(
    checker: ConflictChecker,
    store: Store,
    store_data: AliasStore,
    name: str,
    full_command: str,
    platform_key: str,
    active_shell: str | None,
    force: bool,
    console: Console,
) -> None:
    """Attach a platform-conditional variant to *name* via ``--platform``.

    On an existing alias only the variant is upserted — the base
    ``command`` and all other fields stay untouched, so a variant can be
    added later without re-stating the base.  On a new alias the command
    becomes both the base (the universal fallback) and the variant.
    """
    existing = store_data.aliases.get(name)

    if existing is not None:
        base_arity = placeholder_arity(existing.command)
        variant_arity = placeholder_arity(full_command)
        if not placeholders_compatible(existing.command, full_command):
            print_error(
                f'Variant placeholder arity mismatch for "{name}": base '
                f"{existing.command!r} accepts {base_arity} argument(s), variant "
                f"{full_command!r} accepts {variant_arity}. "
                "All variants must accept the same arguments.",
                console=console,
            )
            raise typer.Exit(1)
        current_variant = existing.command_variants.get(variant_key(platform_key))
        if current_variant is not None and current_variant != full_command and not force:
            print_error(
                f'Variant "{name}" ({platform_key}) already exists.',
                suggestion=f"qwik add {name} <command> --platform {platform_key} --force\n"
                f"qwik edit {name}   to edit all variants interactively",
                console=console,
            )
            raise typer.Exit(1)
        if active_shell is not None:
            _warn_shell_compatibility(active_shell, name, full_command, console)
        # All interactive work happened above; re-read under the store
        # lock and mutate the freshly loaded alias so a concurrent change
        # made while we validated isn't clobbered.
        with store.mutate() as fresh_data:
            fresh_alias = fresh_data.get(name)
            if fresh_alias is None:
                print_error(f'Alias "{name}" no longer exists.', console=console)
                raise typer.Exit(1)
            fresh_alias.command_variants[variant_key(platform_key)] = full_command
            fresh_alias.updated_at = datetime.now(UTC)
        print_success(
            f'Added variant "{name}" ({platform_key}) → {full_command!r}', console=console
        )
        print_info("Run `source <rc>` or open a new terminal to use it.", console=console)
        return

    result = checker.check(name, shell=active_shell)
    _enforce_conflict_gates(result, name, force, None, console)

    if active_shell is not None:
        _warn_shell_compatibility(active_shell, name, full_command, console)

    alias = Alias(
        command=full_command,
        command_variants={variant_key(platform_key): full_command},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    try:
        with store.mutate() as fresh_data:
            fresh_data.add(name, alias, force=force)
    except KeyError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from exc

    print_success(
        f'Added "{name}" → {full_command!r} (base + {platform_key} variant)', console=console
    )
    print_info("Run `source <rc>` or open a new terminal to use it.", console=console)
