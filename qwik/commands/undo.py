"""``qwik undo`` — list, diff, and restore store backups.

Every destructive operation already writes a timestamped backup to
``<config_dir>/backups/`` keeping the last 20. This command is the front
door to that safety net: list what exists, show what a restore would
change, and restore — taking its own backup first, so undo is itself
undoable.
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import tomlkit
import typer

from qwik.core.diff import diff_stores
from qwik.core.models import AliasStore
from qwik.core.store import get_store, read_backup_text
from qwik.ui.prompts import print_error, print_info, print_success, prompt_confirm
from qwik.ui.tables import render_backup_table
from qwik.ui.theme import get_console

if TYPE_CHECKING:
    from pathlib import Path

    from rich.console import Console

    from qwik.core.diff import StoreDiff
    from qwik.core.store import BackupInfo, Store

__all__ = ["undo_command"]


def _parse_backup(backup_path: Path) -> AliasStore | None:
    """Load *backup_path* as an :class:`AliasStore`, or ``None`` if corrupt."""
    try:
        doc = tomlkit.parse(read_backup_text(backup_path))
        return AliasStore.model_validate(doc.unwrap())
    except Exception:
        return None


def _print_diff(diff: StoreDiff, console: Console) -> None:
    """Human-render a :class:`StoreDiff` with ``+``/``-``/``~`` markers."""
    if diff.empty:
        console.print("[qwik.dim]No differences — restoring would change nothing.[/qwik.dim]")
        return
    limit = 20
    shown = 0
    for entry in itertools.chain(diff.added, diff.removed, diff.changed):
        if shown == limit:
            break
        if entry.kind == "add":
            console.print(f"  [qwik.success]+ add[/qwik.success]     {entry.name}")
        elif entry.kind == "remove":
            console.print(f"  [qwik.error]- remove[/qwik.error]   {entry.name}")
        else:
            console.print(
                f"  [qwik.warning]~ change[/qwik.warning]   "
                f"{entry.name}  {entry.old_command!r} → {entry.new_command!r}"
            )
        shown += 1
    total = len(diff.added) + len(diff.removed) + len(diff.changed)
    if total > limit:
        console.print(f"  ... and {total - limit} more")


def _pick_backup(
    store: Store,
    to_stamp: str | None,
    console: Console,
) -> BackupInfo:
    """Resolve which backup to restore; exit cleanly when there is none."""
    backups = store.list_backups()
    if to_stamp is not None:
        target = store.find_backup(to_stamp)
        if target is None:
            print_error(
                f"No backup matching stamp {to_stamp!r}.",
                suggestion="Run `qwik undo --list` to see available stamps.",
                console=console,
            )
            raise typer.Exit(1)
        return target
    if not backups:
        print_error(
            "No valid backups found.",
            suggestion="Backups are written by mutating commands (add, rm, import, ...).",
            console=console,
        )
        raise typer.Exit(1)
    return backups[0]


def _current_store_snapshot(store: Store) -> AliasStore:
    """Load the live store, degrading to an empty store when corrupt."""
    try:
        return store.load(include_overlay=False)
    except RuntimeError:
        # A corrupt live store is exactly when `undo` is most needed, so
        # diff against an empty snapshot instead of refusing to run.
        return AliasStore()


def undo_command(
    to_stamp: str | None = typer.Option(
        None,
        "--to",
        metavar="STAMP",
        help="Restore a specific backup (full or unambiguous partial stamp).",
    ),
    list_only: bool = typer.Option(False, "--list", "-l", help="List available backups."),
    diff_only: bool = typer.Option(
        False, "--diff", help="Show what restoring the newest backup would change."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Restore the alias store from a backup."""
    console = get_console()
    store = get_store()

    if list_only:
        backups = store.list_backups()
        if not backups:
            console.print("[qwik.dim]No backups found.[/qwik.dim]")
            raise typer.Exit(0)
        console.print(render_backup_table(backups, now=datetime.now(UTC)))
        return

    target = _pick_backup(store, to_stamp, console)
    target_store = _parse_backup(target.path)
    if target_store is None:
        # list_backups validates, so this is only reachable when the file
        # changed on disk between listing and reading; refuse rather than
        # restore something unparseable.
        print_error(f"Backup {target.path.name} is corrupt.", console=console)
        raise typer.Exit(1)

    current = _current_store_snapshot(store)
    # Direction matters: current → target, so "+ add" is what the restore
    # would ADD and "- remove" what it would REMOVE, matching the docs.
    diff = diff_stores(current, target_store)

    console.print(f"Restoring [bold]{target.stamp}[/bold] would:")
    _print_diff(diff, console)

    if diff_only:
        raise typer.Exit(0)

    # Confirm BEFORE acquiring the lock so an interactive prompt never
    # holds it (same rule as Store.mutate documents).
    if not yes:
        if diff.empty:
            console.print("Nothing to restore — store already matches this backup.")
            raise typer.Exit(0)
        if not prompt_confirm(
            f"Restore from {target.stamp} ({target.alias_count} aliases)?",
            default=False,
            console=console,
        ):
            print_info("Restore cancelled.", console=console)
            raise typer.Exit(0)

    try:
        store.restore(target.path)
    except RuntimeError as exc:
        print_error(str(exc), console=console)
        raise typer.Exit(1) from exc
    print_success(f"Restored store from {target.path.name}.", console=console)
    print_info(
        "A backup of the pre-restore store was written — run `qwik undo` to revert.",
        console=console,
    )
