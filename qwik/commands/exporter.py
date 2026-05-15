"""``qwik export`` — write aliases to TOML/JSON."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from qwik.core.store import get_store
from qwik.ui.prompts import print_error, print_success

__all__ = ["export_command"]


def export_command(
    path: Path = typer.Argument(..., help="Destination file path."),
    format: Optional[str] = typer.Option(
        None,
        "--format",
        "-f",
        help="toml or json (inferred from extension if omitted).",
    ),
) -> None:
    """Export aliases to a file."""
    store = get_store()
    data = store.load()
    console = Console()

    if not data.aliases:
        print_error("No aliases to export.", console=console)
        raise typer.Exit(1)

    fmt = (format or path.suffix.lstrip(".")).lower()
    if fmt not in ("toml", "json"):
        print_error(f"Unknown format '{fmt}'. Use toml or json.", console=console)
        raise typer.Exit(1)

    if fmt == "toml":
        import tomlkit

        doc = store._store_to_document(data)
        path.write_text(tomlkit.dumps(doc), encoding="utf-8")
    else:
        import json

        path.write_text(
            json.dumps(data.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )

    print_success(f"Exported {len(data.aliases)} aliases to {path}", console=console)
