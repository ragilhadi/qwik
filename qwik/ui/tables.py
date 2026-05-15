"""Rich table renderers for ``qwik list``, ``qwik show``, etc."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.box import SIMPLE_HEAVY
from rich.table import Table


if TYPE_CHECKING:
    from qwik.core.models import Alias, AliasStore

__all__ = [
    "render_list_table",
    "render_alias_detail",
]


def render_list_table(
    store: "AliasStore",
    *,
    tag_filter: str | None = None,
    search_query: str | None = None,
    console=None,
) -> Table:
    """Build a Rich :class:`~rich.table.Table` for ``qwik list``.

    Args:
        store: The alias database.
        tag_filter: If provided, only show aliases containing this tag.
        search_query: If provided, only show aliases whose name, command,
            or tag contains this substring.
        console: Optional Rich console (unused, reserved for future theming).

    Returns:
        A fully populated :class:`~rich.table.Table`.
    """
    del console  # reserved for future use
    table = Table(
        box=SIMPLE_HEAVY,
        header_style="bold",
        show_header=True,
        row_styles=["", "dim"],
    )
    table.add_column("Name", style="qwik.highlight", no_wrap=True)
    table.add_column("Command", no_wrap=False)
    table.add_column("Tag")
    table.add_column("Used", justify="right")
    table.add_column("Last")

    for name in sorted(store.aliases):
        alias = store.aliases[name]
        if tag_filter is not None and tag_filter not in alias.tag:
            continue
        if search_query is not None:
            haystack = f"{name} {alias.command} {' '.join(alias.tag)}"
            if search_query.lower() not in haystack.lower():
                continue
        style = "dim" if not alias.enabled else ""
        table.add_row(
            name,
            alias.command,
            ", ".join(alias.tag),
            str(alias.run_count),
            alias.format_last_used(),
            style=style,
        )

    return table


def render_alias_detail(name: str, alias: "Alias") -> Table:
    """Build a Rich table showing a single alias in detail.

    Args:
        name: Alias identifier.
        alias: The alias definition.

    Returns:
        A two-column detail table.
    """
    table = Table(box=SIMPLE_HEAVY, show_header=False)
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("Name", name)
    table.add_row("Command", alias.command)
    table.add_row("Tags", ", ".join(alias.tag) or "—")
    table.add_row("Description", alias.description or "—")
    table.add_row("Enabled", "yes" if alias.enabled else "no")
    table.add_row("Created", alias.created_at.isoformat())
    table.add_row("Updated", alias.updated_at.isoformat())
    table.add_row("Last used", alias.format_last_used())
    table.add_row("Run count", str(alias.run_count))

    return table
