"""``qwik list`` — pretty table of aliases."""

from __future__ import annotations

from typing import Optional

import typer

from qwik.core.store import get_store
from qwik.ui.tables import render_list_table
from qwik.ui.theme import get_console


def list_command(
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Filter by tag."),
    search: Optional[str] = typer.Option(
        None, "--search", "-s", help="Filter by substring."
    ),
) -> None:
    """Display all aliases in a colored table."""
    store = get_store()
    data = store.load()
    console = get_console()

    if not data.aliases:
        console.print(
            "[dim]No aliases yet. Run `qwik add <name> <command>` to create one.[/dim]"
        )
        raise typer.Exit(0)

    table = render_list_table(data, tag_filter=tag, search_query=search)
    console.print(table)
