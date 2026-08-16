"""``qwik import`` — read aliases from TOML/JSON."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from qwik.core.locking import FileLock
from qwik.core.models import AliasStore
from qwik.core.store import Store, get_store
from qwik.ui.prompts import print_error, print_success, prompt_confirm
from qwik.ui.theme import get_console

__all__ = ["import_command", "preview_and_merge", "preview_import", "merge_into"]


def preview_import(
    incoming: AliasStore,
    data: AliasStore,
    *,
    yes: bool,
    console: Console | None = None,
) -> bool:
    """Show a trust-boundary preview and prompt for confirmation.

    Args:
        incoming: The store parsed from the incoming source.
        data: The current live store.
        yes: If ``True``, skip the confirmation prompt (the warning is
            still shown).
        console: Optional Rich console for output.

    Returns:
        ``True`` if the user confirmed (or ``yes`` was set), ``False`` if
        the user declined the prompt.
    """
    con = console if console is not None else get_console()

    con.print("[qwik.warning]Commands to be imported:[/qwik.warning]")
    for name, alias in list(incoming.aliases.items())[:20]:
        con.print(f"  [bold]{name}[/bold] → {alias.command}")
    if len(incoming.aliases) > 20:
        con.print(f"  ... and {len(incoming.aliases) - 20} more")
    con.print(
        "[qwik.warning]Importing aliases is a trust boundary — "
        "stored commands will run under `shell=True`.[/qwik.warning]"
    )

    existing_names = set(data.aliases)
    incoming_names = set(incoming.aliases)
    new_names = incoming_names - existing_names
    conflict_names = incoming_names & existing_names

    if conflict_names:
        con.print(
            f"[qwik.warning]Conflicts ({len(conflict_names)}):[/qwik.warning] "
            f"{', '.join(sorted(conflict_names))}"
        )
    if new_names:
        con.print(
            f"[qwik.success]New aliases ({len(new_names)}):[/qwik.success] "
            f"{', '.join(sorted(new_names))}"
        )

    if not yes:
        if not prompt_confirm("Apply import?", default=False, console=con):
            return False
    return True


def merge_into(incoming: AliasStore, data: AliasStore) -> tuple[int, int, int]:
    """Merge *incoming* aliases into *data* in place; return counts.

    Args:
        incoming: The store to merge from.
        data: The live store to merge into (mutated in place).

    Returns:
        ``(added, updated, unchanged)`` counts.
    """
    existing_names = set(data.aliases)
    added = 0
    updated = 0
    unchanged = 0
    for name, alias in incoming.aliases.items():
        if name in existing_names:
            if data.aliases[name].command != alias.command:
                updated += 1
            else:
                unchanged += 1
        else:
            added += 1
        data.aliases[name] = alias
    return added, updated, unchanged


def preview_and_merge(
    incoming: AliasStore,
    data: AliasStore,
    store: Store,
    *,
    yes: bool,
    console: Console | None = None,
) -> tuple[int, int, int] | None:
    """Show a trust-boundary preview, prompt for confirmation, then merge.

    Shared by ``qwik import`` and ``qwik sync pull``.  Incoming aliases are
    treated as a trust boundary because their commands run under
    ``shell=True``.

    Args:
        incoming: The store parsed from the incoming source.
        data: The current live store.
        store: The :class:`Store` to persist under backup after merge.
        yes: If ``True``, skip the confirmation prompt.
        console: Optional Rich console for output.

    Returns:
        ``(added, updated, unchanged)`` counts on success, or ``None`` if
        the user declined the prompt.
    """
    if not preview_import(incoming, data, yes=yes, console=console):
        return None
    # The preview above ran against an unlocked, possibly-stale `data` so
    # a confirmation prompt never holds the store lock. Merge against a
    # freshly reloaded store instead, so a concurrent mutation made while
    # the user was reading the preview isn't clobbered by this write.
    with store.mutate() as fresh_data:
        counts = merge_into(incoming, fresh_data)
    return counts


def import_command(
    path: Path = typer.Argument(..., help="Source file path."),
    overwrite: bool = typer.Option(
        False, "--overwrite", "-o", help="Replace entire store."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Import aliases from a TOML or JSON file."""
    store = get_store()
    data = store.load()
    console = get_console()

    if not path.exists():
        print_error(f"File not found: {path}", console=console)
        raise typer.Exit(1)

    suffix = path.suffix.lstrip(".").lower()
    raw = path.read_text(encoding="utf-8")

    try:
        if suffix == "toml":
            import tomlkit

            parsed = dict(tomlkit.parse(raw).unwrap())
        elif suffix == "json":
            import json

            parsed = json.loads(raw)
        else:
            print_error(f"Unknown format '{suffix}'. Use .toml or .json.", console=console)
            raise typer.Exit(1)
        incoming = AliasStore.model_validate(parsed)
    except typer.Exit:
        raise
    except Exception as exc:
        print_error(f"Could not parse {path}: {exc}", console=console)
        raise typer.Exit(1)

    if overwrite:
        if not preview_import(incoming, data, yes=yes, console=console):
            raise typer.Exit(0)
        # Not a mutate() read-modify-write: --overwrite deliberately
        # replaces the whole store regardless of concurrent changes. Still
        # take the lock so this write can't interleave with another
        # process's write and corrupt the file.
        lock = FileLock(store.path.with_suffix(".toml.lock"))
        with lock:
            store.save_with_backup(incoming)
        print_success(f"Imported {len(incoming.aliases)} aliases.", console=console)
        return

    result = preview_and_merge(incoming, data, store, yes=yes, console=console)
    if result is None:
        raise typer.Exit(0)
    print_success(f"Imported {len(incoming.aliases)} aliases.", console=console)
