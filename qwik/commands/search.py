"""``qwik search`` — fuzzy search across aliases."""

from __future__ import annotations

from typing import Optional

import typer
from qwik.core.search import search_aliases
from qwik.core.store import get_store
from qwik.ui.tables import render_list_table
from qwik.ui.theme import get_console


def search_command(
    query: str = typer.Argument(..., help="Search string."),
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Restrict to a tag."),
) -> None:
    """Search aliases by name, command, tag, or description."""
    store = get_store()
    data = store.load()
    console = get_console()

    if not data.aliases:
        console.print("[dim]No aliases yet.[/dim]")
        raise typer.Exit(0)

    results = search_aliases(data, query, tag=tag)
    if not results:
        console.print("[dim]No matches.[/dim]")
        raise typer.Exit(0)

    # Build a filtered AliasStore for rendering
    from qwik.core.models import AliasStore

    filtered = AliasStore()
    for name, alias, _ in results:
        filtered.aliases[name] = alias

    table = render_list_table(filtered)
    console.print(table)
