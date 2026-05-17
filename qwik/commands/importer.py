"""``qwik import`` — read aliases from TOML/JSON."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from qwik.core.models import AliasStore
from qwik.core.store import get_store
from qwik.ui.prompts import print_error, print_success, prompt_confirm

__all__ = ["import_command"]


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
    console = Console()

    if not path.exists():
        print_error(f"File not found: {path}", console=console)
        raise typer.Exit(1)

    suffix = path.suffix.lstrip(".").lower()
    raw = path.read_text(encoding="utf-8")

    if suffix == "toml":
        import tomlkit

        parsed = dict(tomlkit.parse(raw))
    elif suffix == "json":
        import json

        parsed = json.loads(raw)
    else:
        print_error(f"Unknown format '{suffix}'. Use .toml or .json.", console=console)
        raise typer.Exit(1)

    incoming = AliasStore.model_validate(parsed)

    # Diff display
    existing_names = set(data.aliases)
    incoming_names = set(incoming.aliases)
    new_names = incoming_names - existing_names
    conflict_names = incoming_names & existing_names

    if conflict_names:
        console.print(
            f"[qwik.warning]Conflicts ({len(conflict_names)}):[/qwik.warning] {', '.join(sorted(conflict_names))}"
        )
    if new_names:
        console.print(
            f"[qwik.success]New aliases ({len(new_names)}):[/qwik.success] {', '.join(sorted(new_names))}"
        )

    if not yes:
        if not prompt_confirm("Apply import?", default=False, console=console):
            raise typer.Exit(0)

    if overwrite:
        data = incoming
    else:
        for name, alias in incoming.aliases.items():
            data.aliases[name] = alias

    store.save_with_backup(data)
    print_success(f"Imported {len(incoming.aliases)} aliases.", console=console)
