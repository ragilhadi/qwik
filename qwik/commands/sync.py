"""``qwik sync`` — git-backed dotfile sharing across machines.

The sync repo lives at ``<config_dir>/qwik-sync/`` and holds:

- ``aliases.toml`` — a TOML export of the live store (the same format as
  ``qwik export``), committed and pushed on every ``sync push``.
- ``sync.toml`` — the persisted sync config: ``remote_url`` + ``branch``.

``push`` exports the live store → commits → pushes to the remote.
``pull`` pulls the remote → reuses :func:`qwik.commands.importer.preview_and_merge`
to import-merge into the live store under a :class:`FileLock` (the same
trust-boundary preview as ``qwik import``).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import typer
import tomlkit

from qwik.commands.importer import preview_and_merge
from qwik.config import get_config
from qwik.core.git import (
    add_all_and_commit,
    add_remote,
    ahead_behind,
    current_branch,
    git_available,
    has_remote,
    init_repo,
    is_dirty,
    pull as git_pull,
    push as git_push,
    status_short,
)
from qwik.core.locking import FileLock
from qwik.core.models import AliasStore
from qwik.core.store import Store, get_store
from qwik.ui.prompts import print_error, print_info, print_success, print_warning
from qwik.ui.theme import get_console

if TYPE_CHECKING:
    from rich.console import Console

__all__ = ["sync_command"]

_DEFAULT_BRANCH = "main"


def _load_sync_config(repo_dir: Path) -> tuple[str | None, str]:
    """Return ``(remote_url, branch)`` from ``<repo>/sync.toml``.

    If the file is missing, returns ``(None, _DEFAULT_BRANCH)``.
    """
    sync_file = repo_dir / "sync.toml"
    if not sync_file.exists():
        return None, _DEFAULT_BRANCH
    parsed = tomlkit.parse(sync_file.read_text(encoding="utf-8"))
    remote_url = parsed.get("remote_url")
    branch = parsed.get("branch", _DEFAULT_BRANCH)
    remote_str = str(remote_url) if remote_url is not None else None
    branch_str = str(branch) if branch is not None else _DEFAULT_BRANCH
    return remote_str, branch_str


def _save_sync_config(repo_dir: Path, remote_url: str, branch: str) -> None:
    """Write ``remote_url`` + ``branch`` to ``<repo>/sync.toml``."""
    doc = tomlkit.document()
    doc.add("remote_url", remote_url)
    doc.add("branch", branch)
    (repo_dir / "sync.toml").write_text(tomlkit.dumps(doc), encoding="utf-8")


def _export_live_store_to_sync(sync_repo: Path, store: Store) -> int:
    """Write the live store as ``<sync_repo>/aliases.toml``; return alias count."""
    data = store.load()
    doc = Store._store_to_document(data)
    (sync_repo / "aliases.toml").write_text(tomlkit.dumps(doc), encoding="utf-8")
    return len(data.aliases)


def _read_sync_aliases(sync_repo: Path) -> AliasStore:
    """Parse ``<sync_repo>/aliases.toml`` into an :class:`AliasStore`."""
    raw = (sync_repo / "aliases.toml").read_text(encoding="utf-8")
    parsed = dict(tomlkit.parse(raw).unwrap())
    return AliasStore.model_validate(parsed)


def sync_command(
    action: str = typer.Argument(..., help="push|pull|status|init"),
    remote: str | None = typer.Option(
        None, "--remote", help="Git remote URL (sets default on init)."
    ),
    message: str = typer.Option("qwik sync", "--message", "-m"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmations."),
) -> None:
    """Synchronize aliases across machines via a git repo."""
    console = get_console()
    config = get_config()
    sync_repo = config.sync_repo_dir

    if not git_available():
        print_error(
            "git not found on PATH.",
            suggestion="Install git or run 'qwik doctor'.",
            console=console,
        )
        raise typer.Exit(1)

    if action == "init":
        _do_init(sync_repo, remote, message, console=console)
    elif action == "push":
        _do_push(sync_repo, message, console=console)
    elif action == "pull":
        _do_pull(sync_repo, yes, console=console)
    elif action == "status":
        _do_status(sync_repo, console=console)
    else:
        print_error(
            f"Unknown sync action '{action}'.",
            suggestion="Use one of: init, push, pull, status.",
            console=console,
        )
        raise typer.Exit(1)


def _do_init(
    sync_repo: Path,
    remote: str | None,
    message: str,
    *,
    console: "Console | None" = None,
) -> None:
    con = console if console is not None else get_console()
    config = get_config()
    config.ensure_dirs()
    sync_repo.mkdir(parents=True, exist_ok=True)
    init_repo(sync_repo)

    branch = _DEFAULT_BRANCH
    if remote is not None:
        if not has_remote(sync_repo):
            add_remote(sync_repo, remote)
        _save_sync_config(sync_repo, remote, branch)

    store = get_store()
    count = _export_live_store_to_sync(sync_repo, store)
    add_all_and_commit(sync_repo, message)

    if remote is not None:
        print_success(
            f"Sync repo initialized at {sync_repo} (remote={remote}, branch={branch}).",
            console=con,
        )
    else:
        print_success(
            f"Sync repo initialized at {sync_repo}. "
            "Run `qwik sync init --remote <url>` to set a remote.",
            console=con,
        )
    print_info(f"Exported {count} aliases to sync repo.", console=con)


def _do_push(
    sync_repo: Path,
    message: str,
    *,
    console: "Console | None" = None,
) -> None:
    con = console if console is not None else get_console()
    if not sync_repo.exists() or not (sync_repo / ".git").exists():
        print_error(
            "Sync repo not initialized.",
            suggestion="Run `qwik sync init --remote <url>` first.",
            console=con,
        )
        raise typer.Exit(1)

    remote_url, branch = _load_sync_config(sync_repo)
    if remote_url is None:
        print_error(
            "No remote configured for sync repo.",
            suggestion="Run `qwik sync init --remote <url>` to set one.",
            console=con,
        )
        raise typer.Exit(1)

    store = get_store()
    count = _export_live_store_to_sync(sync_repo, store)

    if is_dirty(sync_repo):
        add_all_and_commit(sync_repo, message)
        git_push(sync_repo, "origin", branch)
        print_success(
            f"Pushed {count} aliases to {remote_url} ({branch}).",
            console=con,
        )
    else:
        print_info("Nothing to push — sync repo is clean.", console=con)


def _do_pull(
    sync_repo: Path,
    yes: bool,
    *,
    console: "Console | None" = None,
) -> None:
    con = console if console is not None else get_console()
    if not sync_repo.exists() or not (sync_repo / ".git").exists():
        print_error(
            "Sync repo not initialized.",
            suggestion="Run `qwik sync init --remote <url>` first.",
            console=con,
        )
        raise typer.Exit(1)

    remote_url, branch = _load_sync_config(sync_repo)
    if remote_url is None:
        print_error(
            "No remote configured for sync repo.",
            suggestion="Run `qwik sync init --remote <url>` to set one.",
            console=con,
        )
        raise typer.Exit(1)

    git_pull(sync_repo, "origin", branch)

    incoming = _read_sync_aliases(sync_repo)

    store = get_store()
    lock = FileLock(store.path.with_suffix(".toml.lock"))
    with lock:
        data = store.load()
        result = preview_and_merge(incoming, data, store, yes=yes, console=con)
    if result is None:
        raise typer.Exit(0)
    added, updated, unchanged = result
    print_success(
        f"Pulled {len(incoming.aliases)} aliases from {remote_url} ({branch}): "
        f"{added} added, {updated} updated, {unchanged} unchanged.",
        console=con,
    )


def _do_status(
    sync_repo: Path,
    *,
    console: "Console | None" = None,
) -> None:
    con = console if console is not None else get_console()
    if not sync_repo.exists() or not (sync_repo / ".git").exists():
        print_info("Sync repo: not initialized.", console=con)
        return

    remote_url, branch = _load_sync_config(sync_repo)
    try:
        cur_branch = current_branch(sync_repo)
    except RuntimeError as exc:
        print_warning(f"Could not read sync repo branch: {exc}", console=con)
        cur_branch = branch

    dirty = is_dirty(sync_repo)
    short = status_short(sync_repo)

    if remote_url is None:
        con.print(f"[bold]Sync repo:[/bold] {sync_repo}")
        con.print(f"  Branch: {cur_branch}")
        con.print("  Remote: [qwik.warning]not configured[/qwik.warning]")
    else:
        con.print(f"[bold]Sync repo:[/bold] {sync_repo}")
        con.print(f"  Branch: {cur_branch}")
        con.print(f"  Remote: {remote_url}")
        try:
            behind, ahead = ahead_behind(sync_repo, "origin", branch)
            con.print(f"  Ahead/behind origin/{branch}: {ahead} ahead, {behind} behind")
        except RuntimeError as exc:
            con.print(f"  Ahead/behind: [qwik.warning]unavailable ({exc})[/qwik.warning]")

    con.print(f"  Working tree: {'dirty' if dirty else 'clean'}")
    if dirty and short:
        con.print(f"  [qwik.warning]{short}[/qwik.warning]")

    aliases_file = sync_repo / "aliases.toml"
    if aliases_file.exists():
        try:
            incoming = _read_sync_aliases(sync_repo)
            con.print(f"  Aliases in sync repo: {len(incoming.aliases)}")
        except Exception as exc:
            con.print(f"  Aliases in sync repo: [qwik.warning]unreadable ({exc})[/qwik.warning]")
    else:
        con.print("  Aliases in sync repo: 0 (no aliases.toml yet)")