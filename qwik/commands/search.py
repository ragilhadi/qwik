"""``qwik search`` — fuzzy search across aliases."""

from __future__ import annotations

import typer

from qwik.core.search import search_aliases
from qwik.core.store import get_store
from qwik.ui.tables import render_list_table
from qwik.ui.theme import get_console


def search_command(
    query: str = typer.Argument(..., help="Search string."),
    tag: str | None = typer.Option(None, "--tag", "-t", help="Restrict to a tag."),
    group: str | None = typer.Option(None, "--group", "-g", help="Restrict to a group."),
) -> None:
    """Search aliases by name, command, tag, group, or description."""
    store = get_store()
    data = store.load()
    console = get_console()

    if not data.all_aliases():
        console.print("[dim]No aliases yet.[/dim]")
        raise typer.Exit(0)

    results = search_aliases(data, query, tag=tag, group=group)
    if not results:
        console.print("[dim]No matches.[/dim]")
        raise typer.Exit(0)

    # Build a filtered AliasStore for rendering, preserving provenance:
    # a result that came from data.aliases (the user's own store) stays
    # there so render_list_table's "(overlay)" marker is accurate; a
    # result found only via the overlay goes into overlay_aliases.
    from qwik.core.models import AliasStore

    filtered = AliasStore()
    for name, alias, _ in results:
        if name in data.aliases:
            filtered.aliases[name] = alias
        else:
            filtered.overlay_aliases[name] = alias

    table = render_list_table(filtered)
    console.print(table)
