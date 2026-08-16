"""``qwik list`` — pretty table of aliases."""

from __future__ import annotations

import typer

from qwik.core.store import get_store
from qwik.ui.tables import render_list_table
from qwik.ui.theme import get_console


def list_command(
    tag: str | None = typer.Option(None, "--tag", "-t", help="Filter by tag."),
    group: str | None = typer.Option(None, "--group", "-g", help="Filter by group."),
    search: str | None = typer.Option(None, "--search", "-s", help="Filter by substring."),
) -> None:
    """Display all aliases in a colored table."""
    store = get_store()
    data = store.load()
    console = get_console()

    if not data.all_aliases():
        console.print("[dim]No aliases yet. Run `qwik add <name> <command>` to create one.[/dim]")
        raise typer.Exit(0)

    table = render_list_table(data, tag_filter=tag, group_filter=group, search_query=search)
    console.print(table)
