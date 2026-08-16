"""``qwik overlay`` — team/shared read-only overlay store management."""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path
from typing import TYPE_CHECKING

import tomlkit
import typer

from qwik.commands.importer import preview_import
from qwik.config import Config, get_config
from qwik.core.git import (
    clone as git_clone,
)
from qwik.core.git import (
    fetch as git_fetch,
)
from qwik.core.git import (
    git_available,
)
from qwik.core.git import (
    reset_hard as git_reset_hard,
)
from qwik.core.git import (
    show_file as git_show_file,
)
from qwik.core.models import AliasStore
from qwik.core.store import get_store
from qwik.ui.prompts import (
    print_error,
    print_info,
    print_success,
    print_warning,
    prompt_confirm,
)
from qwik.ui.theme import get_console

if TYPE_CHECKING:
    from collections.abc import Callable

    from rich.console import Console

__all__ = ["overlay_command"]

_DEFAULT_BRANCH = "main"


def _force_rmtree(path: Path) -> None:
    """Best-effort recursive delete that also clears Windows' read-only bit.

    git marks objects under ``.git/objects/pack`` (and sometimes more)
    read-only on Windows after a clone. A bare ``shutil.rmtree`` fails on
    those with ``PermissionError`` there — never on POSIX, where mode
    bits don't block unlink the same way — so pairing it with
    ``ignore_errors=True`` silently left the clone on disk while every
    caller believed cleanup had succeeded.
    """

    def _clear_readonly_and_retry(
        func: Callable[[str], object], target: str, _exc_info: BaseException
    ) -> None:
        try:
            os.chmod(target, stat.S_IWRITE)
            func(target)
        except OSError:
            pass

    shutil.rmtree(path, onexc=_clear_readonly_and_retry)


def _load_overlay_config(config_file: Path) -> tuple[str | None, str, bool]:
    """Return ``(url, branch, auto_update)`` from overlay config."""
    if not config_file.exists():
        return None, _DEFAULT_BRANCH, True
    parsed = tomlkit.parse(config_file.read_text(encoding="utf-8"))
    url = parsed.get("url")
    branch = str(parsed.get("branch", _DEFAULT_BRANCH))
    auto_update = bool(parsed.get("auto_update", True))
    url_str = str(url) if url is not None else None
    return url_str, branch, auto_update


def _save_overlay_config(config_file: Path, url: str, branch: str) -> None:
    doc = tomlkit.document()
    doc.add("url", url)
    doc.add("branch", branch)
    doc.add("auto_update", True)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(tomlkit.dumps(doc), encoding="utf-8")


def _read_overlay_aliases(overlay_file: Path) -> AliasStore:
    from qwik.core.migrations import migrate

    raw = overlay_file.read_text(encoding="utf-8")
    data = dict(tomlkit.parse(raw).unwrap())
    data = migrate(data)
    return AliasStore.model_validate(data)


def overlay_command(
    action: str = typer.Argument(..., help="add|remove|update|list|copy"),
    name: str | None = typer.Argument(None, help="Alias name (for copy)."),
    url: str | None = typer.Option(None, "--url", help="Overlay repo URL (for add)."),
    branch: str = typer.Option(_DEFAULT_BRANCH, "--branch", help="Overlay repo branch."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation (for add/update)."),
) -> None:
    """Manage the team/shared read-only overlay store."""
    console = get_console()
    config = get_config()

    if action == "add":
        effective_url = url if url is not None else name
        _do_add(config, effective_url, branch, yes=yes, console=console)
    elif action == "remove":
        _do_remove(config, console=console)
    elif action == "update":
        _do_update(config, yes=yes, console=console)
    elif action == "list":
        _do_list(config, console=console)
    elif action == "copy":
        if name is None:
            print_error("Usage: qwik overlay copy <name>", console=console)
            raise typer.Exit(1)
        _do_copy(config, name, console=console)
    else:
        print_error(
            f"Unknown overlay action '{action}'.",
            suggestion="Use one of: add, remove, update, list, copy.",
            console=console,
        )
        raise typer.Exit(1)


def _do_add(
    config: Config,
    url: str | None,
    branch: str,
    *,
    yes: bool,
    console: Console,
) -> None:
    if url is None:
        print_error("Usage: qwik overlay add --url <git-url>", console=console)
        raise typer.Exit(1)

    if not git_available():
        print_error(
            "git not found on PATH.",
            suggestion="Install git or run 'qwik doctor'.",
            console=console,
        )
        raise typer.Exit(1)

    overlay_repo = config.overlay_repo_dir
    if overlay_repo.exists():
        print_error(
            "Overlay already configured.",
            suggestion="Run `qwik overlay remove` first, or " "`qwik overlay update` to refresh.",
            console=console,
        )
        raise typer.Exit(1)

    overlay_repo.parent.mkdir(parents=True, exist_ok=True)
    try:
        # A fresh clone (rather than init + remote add + pull) always
        # leaves a proper upstream tracking branch and can never enter a
        # merge-conflict state — the overlay is read-only by design, so
        # there is nothing to merge.
        git_clone(url, overlay_repo, branch)
    except RuntimeError as exc:
        print_error(f"Failed to clone overlay: {exc}", console=console)
        _force_rmtree(overlay_repo)
        raise typer.Exit(1) from exc

    overlay_file = config.overlay_aliases_file
    if not overlay_file.exists():
        print_warning(
            f"No aliases.toml found in overlay repo at {overlay_file}.",
            console=console,
        )
        _save_overlay_config(config.overlay_config_file, url, branch)
        print_info("Run `qwik overlay update` to refresh.", console=console)
        return

    try:
        incoming = _read_overlay_aliases(overlay_file)
    except Exception as exc:
        print_error(f"Could not read overlay aliases: {exc}", console=console)
        _force_rmtree(overlay_repo)
        raise typer.Exit(1) from exc

    store = get_store()
    user_data = store.load()
    # Same trust-boundary preview `qwik import` and `qwik sync pull`
    # show — the overlay is the most remote of the three ingestion
    # paths (a repo controlled by someone else, refreshed on demand),
    # and was previously the only one without a gate. Declining leaves
    # nothing configured, matching import's "no partial state" behavior.
    if not preview_import(incoming, user_data, yes=yes, console=console):
        _force_rmtree(overlay_repo)
        raise typer.Exit(0)

    _save_overlay_config(config.overlay_config_file, url, branch)
    print_success(
        f"Overlay configured with {len(incoming.aliases)} aliases.",
        console=console,
    )
    print_info("Run `qwik overlay update` to refresh.", console=console)


def _do_remove(config: Config, *, console: Console) -> None:
    config_file = config.overlay_config_file
    overlay_repo = config.overlay_repo_dir
    if not config_file.exists() and not overlay_repo.exists():
        print_error("No overlay configured.", console=console)
        raise typer.Exit(1)

    if config_file.exists():
        config_file.unlink()
    if overlay_repo.exists():
        _force_rmtree(overlay_repo)
    print_success("Overlay removed.", console=console)


def _do_update(config: Config, *, yes: bool, console: Console) -> None:
    config_file = config.overlay_config_file
    overlay_repo = config.overlay_repo_dir

    if not config_file.exists():
        print_error("No overlay configured.", console=console)
        raise typer.Exit(1)

    url, branch, _ = _load_overlay_config(config_file)

    if not git_available():
        print_error("git not found on PATH.", console=console)
        raise typer.Exit(1)

    try:
        git_fetch(overlay_repo, "origin", branch)
    except RuntimeError as exc:
        print_error(f"Failed to fetch overlay: {exc}", console=console)
        raise typer.Exit(1) from exc

    incoming = _read_incoming_at_ref(overlay_repo, f"origin/{branch}")
    current = (
        _read_overlay_aliases(config.overlay_aliases_file)
        if config.overlay_aliases_file.exists()
        else AliasStore()
    )

    added = sorted(set(incoming.aliases) - set(current.aliases))
    removed = sorted(set(current.aliases) - set(incoming.aliases))
    changed = sorted(
        n
        for n in set(incoming.aliases) & set(current.aliases)
        if incoming.aliases[n].command != current.aliases[n].command
    )

    if not added and not removed and not changed:
        print_info(f"Overlay already up to date ({url}, {branch}).", console=console)
        return

    # Same trust-boundary preview qwik import/sync pull show, plus the
    # removal set (an update that only lists additions would hide that
    # an alias is disappearing from every member's shell hook).
    console.print(f"[qwik.warning]Overlay changes from {url} ({branch}):[/qwik.warning]")
    if added:
        console.print(f"[qwik.success]Added ({len(added)}):[/qwik.success] {', '.join(added)}")
    if changed:
        console.print(
            f"[qwik.warning]Changed ({len(changed)}):[/qwik.warning] {', '.join(changed)}"
        )
    if removed:
        console.print(f"[qwik.error]Removed ({len(removed)}):[/qwik.error] {', '.join(removed)}")
    console.print(
        "[qwik.warning]Overlay aliases are a trust boundary — stored commands "
        "will run under `shell=True` once rendered into your shell hook.[/qwik.warning]"
    )
    if not yes:
        if not prompt_confirm("Apply overlay update?", default=False, console=console):
            raise typer.Exit(0)

    # A hard reset (rather than a merge pull) is correct because the
    # overlay is read-only by design: the local checkout should always
    # exactly mirror the remote branch, never diverge from it.
    git_reset_hard(overlay_repo, f"origin/{branch}")
    print_success(
        f"Overlay updated from {url} ({branch}): "
        f"{len(added)} added, {len(changed)} changed, {len(removed)} removed.",
        console=console,
    )


def _read_incoming_at_ref(overlay_repo: Path, ref: str) -> AliasStore:
    """Read ``aliases.toml`` from *ref* without touching the working tree.

    Used to preview an incoming overlay update after ``fetch`` but before
    ``reset --hard`` applies it.
    """
    from qwik.core.migrations import migrate

    try:
        raw = git_show_file(overlay_repo, ref, "aliases.toml")
    except RuntimeError:
        return AliasStore()
    data = dict(tomlkit.parse(raw).unwrap())
    data = migrate(data)
    return AliasStore.model_validate(data)


def _do_list(config: Config, *, console: Console) -> None:
    config_file = config.overlay_config_file

    if not config_file.exists():
        print_info("No overlay configured.", console=console)
        return

    url, branch, auto_update = _load_overlay_config(config_file)
    console.print(f"[bold]Overlay:[/bold] {url} ({branch})")
    console.print(f"  Auto-update: {'on' if auto_update else 'off'}")

    overlay_file = config.overlay_aliases_file
    if not overlay_file.exists():
        console.print("  Aliases: 0 (no aliases.toml in overlay repo)")
        return

    try:
        incoming = _read_overlay_aliases(overlay_file)
        store = get_store()
        user_data = store.load()
        console.print(f"  Aliases: {len(incoming.aliases)}")
        for n in sorted(incoming.aliases):
            marker = "[dim](user)[/dim]" if n in user_data.aliases else "[dim](overlay)[/dim]"
            console.print(f"    {n} {marker}")
    except Exception as exc:
        console.print(f"  Aliases: [qwik.warning]unreadable ({exc})[/qwik.warning]")


def _do_copy(config: Config, name: str, *, console: Console) -> None:
    overlay_file = config.overlay_aliases_file
    if overlay_file.exists():
        try:
            incoming = _read_overlay_aliases(overlay_file)
        except Exception as exc:
            print_error(f"Could not read overlay: {exc}", console=console)
            raise typer.Exit(1) from exc
    else:
        incoming = AliasStore()

    if name not in incoming.aliases:
        print_error(f"'{name}' is not an overlay alias.", console=console)
        raise typer.Exit(1)

    store = get_store()
    with store.mutate() as data:
        if name in data.aliases:
            print_warning(f"'{name}' already exists in user store.", console=console)
            raise typer.Exit(0)

        data.add(name, incoming.aliases[name])
    print_success(f"Copied '{name}' from overlay to user store.", console=console)
