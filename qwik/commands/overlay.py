"""``qwik overlay`` — team/shared read-only overlay store management."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import tomlkit
import typer

from qwik.config import Config, get_config
from qwik.core.git import (
    add_remote,
    git_available,
    has_remote,
    init_repo,
    pull as git_pull,
)
from qwik.core.models import AliasStore
from qwik.core.store import get_store
from qwik.ui.prompts import print_error, print_info, print_success, print_warning
from qwik.ui.theme import get_console

if TYPE_CHECKING:
    from rich.console import Console  # noqa: F401

__all__ = ["overlay_command"]

_DEFAULT_BRANCH = "main"


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
    name: str | None = typer.Argument(
        None, help="Alias name (for copy)."
    ),
    url: str | None = typer.Option(None, "--url", help="Overlay repo URL (for add)."),
    branch: str = typer.Option(_DEFAULT_BRANCH, "--branch", help="Overlay repo branch."),
) -> None:
    """Manage the team/shared read-only overlay store."""
    console = get_console()
    config = get_config()

    if action == "add":
        effective_url = url if url is not None else name
        _do_add(config, effective_url, branch, console=console)
    elif action == "remove":
        _do_remove(config, console=console)
    elif action == "update":
        _do_update(config, console=console)
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
    console: "Console",
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
    overlay_repo.mkdir(parents=True, exist_ok=True)

    if not (overlay_repo / ".git").exists():
        init_repo(overlay_repo)

    if not has_remote(overlay_repo):
        add_remote(overlay_repo, url)
    _save_overlay_config(config.overlay_config_file, url, branch)

    try:
        git_pull(overlay_repo, "origin", branch)
    except RuntimeError as exc:
        print_error(f"Failed to pull overlay: {exc}", console=console)
        raise typer.Exit(1)

    overlay_file = config.overlay_aliases_file
    if not overlay_file.exists():
        print_warning(
            f"No aliases.toml found in overlay repo at {overlay_file}.",
            console=console,
        )
    else:
        try:
            incoming = _read_overlay_aliases(overlay_file)
            print_success(
                f"Overlay configured with {len(incoming.aliases)} aliases.",
                console=console,
            )
        except Exception as exc:
            print_error(f"Could not read overlay aliases: {exc}", console=console)

    print_info("Run `qwik overlay update` to refresh.", console=console)


def _do_remove(config: Config, *, console: "Console") -> None:
    config_file = config.overlay_config_file
    overlay_repo = config.overlay_repo_dir
    if not config_file.exists() and not overlay_repo.exists():
        print_error("No overlay configured.", console=console)
        raise typer.Exit(1)

    import shutil

    if config_file.exists():
        config_file.unlink()
    if overlay_repo.exists():
        shutil.rmtree(overlay_repo, ignore_errors=True)
    print_success("Overlay removed.", console=console)


def _do_update(config: Config, *, console: "Console") -> None:
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
        git_pull(overlay_repo, "origin", branch)
        print_success(f"Overlay updated from {url} ({branch}).", console=console)
    except RuntimeError as exc:
        print_error(f"Failed to update overlay: {exc}", console=console)
        raise typer.Exit(1)


def _do_list(config: Config, *, console: "Console") -> None:
    config_file = config.overlay_config_file
    overlay_repo = config.overlay_repo_dir

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


def _do_copy(config: Config, name: str, *, console: "Console") -> None:
    overlay_file = config.overlay_aliases_file
    if overlay_file.exists():
        try:
            incoming = _read_overlay_aliases(overlay_file)
        except Exception as exc:
            print_error(f"Could not read overlay: {exc}", console=console)
            raise typer.Exit(1)
    else:
        incoming = AliasStore()

    if name not in incoming.aliases:
        print_error(f"'{name}' is not an overlay alias.", console=console)
        raise typer.Exit(1)

    store = get_store()
    data = store.load()

    if name in data.aliases:
        print_warning(f"'{name}' already exists in user store.", console=console)
        raise typer.Exit(0)

    data.add(name, incoming.aliases[name])
    store.save_with_backup(data)
    print_success(f"Copied '{name}' from overlay to user store.", console=console)
