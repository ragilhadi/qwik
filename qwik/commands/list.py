"""``qwik list`` — pretty table of aliases."""

from __future__ import annotations

import typer

from qwik.core.platform import validate_platform
from qwik.core.store import get_store
from qwik.ui.prompts import print_error
from qwik.ui.tables import render_list_table
from qwik.ui.theme import get_console


def list_command(
    tag: str | None = typer.Option(None, "--tag", "-t", help="Filter by tag."),
    group: str | None = typer.Option(None, "--group", "-g", help="Filter by group."),
    search: str | None = typer.Option(None, "--search", "-s", help="Filter by substring."),
    platform: str | None = typer.Option(
        None,
        "--platform",
        "-p",
        help="Preview command resolution for another platform (linux, macos, windows).",
    ),
) -> None:
    """Display all aliases in a colored table."""
    store = get_store()
    data = store.load()
    console = get_console()

    # `list_command()` is also invoked directly from the `-l` shortcut in
    # the main callback, bypassing Click's option parsing — the positional
    # defaults are then raw OptionInfo objects rather than the None they
    # carry. Only trust real strings.
    requested_platform: str | None = None
    if isinstance(platform, str):
        try:
            requested_platform = validate_platform(platform)
        except ValueError as exc:
            print_error(str(exc), console=console)
            raise typer.Exit(1) from exc

    if not data.all_aliases():
        console.print("[dim]No aliases yet. Run `qwik add <name> <command>` to create one.[/dim]")
        raise typer.Exit(0)

    table = render_list_table(
        data, tag_filter=tag, group_filter=group, search_query=search, platform=requested_platform
    )
    if requested_platform:
        console.print(f"[dim]Commands resolved for platform: {requested_platform}[/dim]")
    console.print(table)
