"""``qwik project`` — manage project-scoped aliases from ``.qwik.toml``.

Precedence: project → user → overlay.  A ``.qwik.toml`` is inert until
explicitly trusted (it arrives by ``git clone``, so it is untrusted by
definition); trust is per absolute path plus a SHA-256 content hash and
reverts to inert when the file changes.

Commands:

- ``qwik project init`` — scaffold a ``.qwik.toml`` in the current directory
- ``qwik project status`` — show discovery result and trust state
- ``qwik project trust`` — opt in to this directory's file
- ``qwik project untrust`` — remove the trust record
- ``qwik project list`` — list the trusted project layer's aliases
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from qwik.core.project import (
    PROJECT_FILE_NAME,
    discover_project,
    load_trust_store,
    save_trust_store,
)
from qwik.core.store import get_store
from qwik.ui.prompts import print_error, print_info, print_success, prompt_confirm
from qwik.ui.theme import get_console

__all__ = ["project_command"]

_TRUST_PROMPT = (
    "This file was not created by you. Its aliases will run with your"
    " user's full privileges inside this directory. Trust it?"
)

_SCAFFOLD = """\
# qwik project file — aliases scoped to this directory tree.
# Precedence: project -> user -> overlay.  Inert until
# `qwik project trust` is run here.
version = 1

[aliases.example]
command = "echo hello from the project"
description = "Replace me"
"""


def project_command(
    action: str = typer.Argument(..., help="init | status | trust | untrust | list"),
) -> None:
    """Manage project-scoped aliases (``.qwik.toml``)."""
    console = get_console()
    actions = {
        "init": _action_init,
        "status": _action_status,
        "trust": _action_trust,
        "untrust": _action_untrust,
        "list": _action_list,
    }
    handler = actions.get(action)
    if handler is None:
        print_error(
            f'Unknown action "{action}".',
            suggestion="Use one of: init, status, trust, untrust, list",
            console=console,
        )
        raise typer.Exit(1)
    handler(console)


def _action_init(console: object) -> None:
    """Scaffold a ``.qwik.toml`` in the current directory."""
    console = get_console()
    target = Path.cwd() / PROJECT_FILE_NAME
    if target.exists():
        print_error(
            f"{PROJECT_FILE_NAME} already exists in this directory.",
            console=console,
        )
        raise typer.Exit(1)
    target.write_text(_SCAFFOLD, encoding="utf-8")
    print_success(f"Scaffolded {target}", console=console)
    print_info(
        "Inert until trusted: run `qwik project trust` here when ready.",
        console=console,
    )


def _action_status(console: object) -> None:
    """Report discovery, trust state, and layer contents."""
    console = get_console()
    layer = discover_project()
    if layer is None:
        print_info(f"No {PROJECT_FILE_NAME} found from {Path.cwd()} upward.", console=console)
        raise typer.Exit(0)
    table = Table(title=f"Project layer — {layer.path}")
    table.add_column("Property")
    table.add_column("Value")
    table.add_column("Value style")
    table.add_column("Value detail")
    trust_label = {
        "trusted": "trusted (hash matches)",
        "stale": "TRUST REVOKED — file changed since trust; re-run `qwik project trust`",
        "untrusted": "untrusted — inert until `qwik project trust`",
        "none": "-",
    }[layer.trust]
    table.add_row("File", str(layer.path), "", "")
    table.add_row("Trust", trust_label, "", "")
    table.add_row("SHA-256", layer.sha256[:16] + "…", "", "")
    if layer.parse_error:
        table.add_row("Parse error", layer.parse_error, "", "")
    elif layer.file:
        table.add_row("Aliases", str(len(layer.file.aliases)), "", "")
    console.print(table)


def _action_trust(console: object) -> None:
    """Record trust for the discovered ``.qwik.toml`` after confirmation."""
    console = get_console()
    layer = discover_project()
    if layer is None:
        print_error(
            f"No {PROJECT_FILE_NAME} found from {Path.cwd()} upward.",
            console=console,
        )
        raise typer.Exit(1)
    if layer.parse_error:
        print_error(
            f"{layer.path} does not parse: {layer.parse_error}",
            console=console,
        )
        raise typer.Exit(1)
    if layer.trust == "trusted":
        print_info(f"{layer.path} is already trusted (unchanged).", console=console)
        return
    if layer.trust == "stale":
        print_info(
            f"{layer.path} changed since you trusted it — reviewing again.",
            console=console,
        )
    if layer.file is None:
        raise typer.Exit(1)
    if not prompt_confirm(_TRUST_PROMPT, default=False, console=console):
        print_info("Not trusted; the file stays inert.", console=console)
        raise typer.Exit(0)

    from qwik.core.project import TrustState

    store = load_trust_store()
    store.trusted[str(layer.path)] = TrustState(sha256=layer.sha256)
    save_trust_store(store)
    print_success(f"Trusted {layer.path} (sha256 {layer.sha256[:16]}…).", console=console)
    print_info("Open a new terminal or run `qwik init <shell>` to refresh.", console=console)


def _action_untrust(console: object) -> None:
    """Remove the trust record for the discovered file."""
    console = get_console()
    layer = discover_project()
    path_str = str(layer.path) if layer else str(Path.cwd() / PROJECT_FILE_NAME)
    store = load_trust_store()
    if path_str not in store.trusted:
        print_info(f"No trust record for {path_str}.", console=console)
        return
    del store.trusted[path_str]
    save_trust_store(store)
    print_success(f"Removed trust for {path_str}.", console=console)
    print_info("Any aliases it defines are inert again.", console=console)


def _action_list(console: object) -> None:
    """List the merged view with project-layer marks."""
    console = get_console()
    from qwik.ui.tables import render_list_table

    data = get_store().load()
    if not data.project_aliases:
        print_info(
            f"No trusted project layer active from {Path.cwd()}.",
            console=console,
        )
        raise typer.Exit(0)
    table = render_list_table(data, console=console)
    console.print(table)
