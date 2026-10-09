"""Rich table renderers for ``qwik list``, ``qwik show``, ``qwik stats``."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from rich.box import SIMPLE_HEAVY
from rich.console import Console
from rich.table import Table

from qwik.core.models import Alias
from qwik.core.stats import (
    TIME_SAVED_LABEL,
    AliasUsage,
    StatsOverview,
    estimate_time_saved,
    format_timedelta,
)

if TYPE_CHECKING:
    from datetime import timedelta

    from qwik.core.models import AliasStore

__all__ = [
    "render_alias_detail",
    "render_list_table",
    "render_stats",
]


def render_list_table(
    store: AliasStore,
    *,
    tag_filter: str | None = None,
    group_filter: str | None = None,
    search_query: str | None = None,
    console: Console | None = None,
) -> Table:
    """Build a Rich :class:`~rich.table.Table` for ``qwik list``.

    Args:
        store: The alias database.
        tag_filter: If provided, only show aliases containing this tag.
        group_filter: If provided, only show aliases in this group.
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
    table.add_column("Group")
    table.add_column("Tag")
    table.add_column("Used", justify="right")
    table.add_column("Last")

    # all_aliases() merges the overlay in, with the user's own store
    # taking precedence for any name defined in both — the same view
    # `qwik init`, `qwik pick`, and `qwik search` already use, and the
    # one the shell hook actually renders from.
    merged = store.all_aliases()
    for name in sorted(merged):
        alias = merged[name]
        if tag_filter is not None and tag_filter not in alias.tag:
            continue
        if group_filter is not None and alias.group != group_filter:
            continue
        if search_query is not None:
            haystack = f"{name} {alias.command} {' '.join(alias.tag)}"
            if search_query.lower() not in haystack.lower():
                continue
        style = "dim" if not alias.enabled else ""
        is_overlay = name not in store.aliases
        display_name = f"{name} [dim](overlay)[/dim]" if is_overlay else name
        table.add_row(
            display_name,
            alias.command,
            alias.group or "—",
            ", ".join(alias.tag),
            str(alias.run_count),
            alias.format_last_used(),
            style=style,
        )

    return table


def render_alias_detail(name: str, alias: Alias) -> Table:
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
    table.add_row("Group", alias.group or "—")
    table.add_row("Tags", ", ".join(alias.tag) or "—")
    table.add_row("Description", alias.description or "—")
    table.add_row("Enabled", "yes" if alias.enabled else "no")
    table.add_row("Created", alias.created_at.isoformat())
    table.add_row("Updated", alias.updated_at.isoformat())
    table.add_row("Last used", alias.format_last_used())
    table.add_row("Run count", str(alias.run_count))

    return table


def render_stats(
    store: AliasStore,
    *,
    top_rows: list[AliasUsage] | None = None,
    unused_rows: list[AliasUsage] | None = None,
    overview: StatsOverview | None = None,
    since: timedelta | None = None,
    now: Any = None,
) -> Table:
    """Build a Rich table for ``qwik stats`` views.

    Exactly one of *top_rows*, *unused_rows*, or *overview* drives the
    rendered view; ``None`` means "not this view", while an empty list
    renders the view with an empty-state line.

    Args:
        store: The alias database (used for the total/summary header).
        top_rows: Rows for the ``--top N`` view.
        unused_rows: Rows for the ``--unused`` view.
        overview: Aggregated overview (bare ``qwik stats``).
        since: The ``--since`` window, when one was given.
        now: Current time used to compute the view.

    Returns:
        A fully populated :class:`~rich.table.Table`.
    """
    if now is None:
        now = datetime.now(UTC)

    table = Table(box=SIMPLE_HEAVY, show_header=False, padding=(0, 1))
    table.add_column(style="bold", no_wrap=True)
    table.add_column()

    merged = store.all_aliases()
    total_aliases = len(merged)
    total_runs = sum(a.run_count for a in merged.values())

    if top_rows is not None:
        header = f"  {total_aliases} alias{'es' if total_aliases != 1 else ''} · {total_runs} runs"
        table.add_row("Top used", header)
        if not top_rows:
            table.add_row("", "[qwik.dim]No usage recorded yet — run some aliases![/qwik.dim]")
        for i, row in enumerate(top_rows, 1):
            saved = format_timedelta(
                estimate_time_saved([row]),
            )
            name = f"{row.name} [dim](overlay)[/dim]" if row.is_overlay else row.name
            last = row.alias.format_last_used()
            table.add_row(f"  {i}.", f"{name}  {row.run_count} runs  {saved}  last: {last}")
        return table

    if unused_rows is not None:
        if since is not None:
            days = int(since.total_seconds() // 86400)
            window = f"not run in the last {days} day{'s' if days != 1 else ''}"
        else:
            window = "never used"
        header = (
            f"  {len(unused_rows)} unused alias{'es' if len(unused_rows) != 1 else ''} ({window})"
        )
        table.add_row("Unused", header)
        for row in unused_rows:
            name = f"{row.name} [dim](overlay)[/dim]" if row.is_overlay else row.name
            marker = "never" if row.alias.last_used is None else row.alias.format_last_used()
            table.add_row("  •", f"{name}  last: {marker}")
        if unused_rows:
            table.add_row("", "[qwik.dim]→ qwik stats --unused --prune  to remove them[/qwik.dim]")
        return table

    assert overview is not None
    table.add_row(
        "",
        f"  {overview.total_aliases} alias{'es' if overview.total_aliases != 1 else ''}"
        f" · {overview.total_runs} runs"
        f" · {overview.recent_used} used this week",
    )
    if not overview.total_runs:
        table.add_row("", "[qwik.dim]No usage recorded yet — run some aliases![/qwik.dim]")

    top_in_overview = sorted(merged.items(), key=lambda kv: (-kv[1].run_count, kv[0]))[:5]
    if any(a.run_count for _, a in top_in_overview):
        table.add_row("Most used", "")
        for i, (name, alias) in enumerate(top_in_overview, 1):
            if alias.run_count == 0:
                continue
            is_overlay = name not in store.aliases
            display = f"{name} [dim](overlay)[/dim]" if is_overlay else name
            saved = format_timedelta(
                estimate_time_saved([AliasUsage(name=name, alias=alias, is_overlay=is_overlay)])
            )
            table.add_row(
                f"  {i}.",
                f"{display}  {alias.run_count} runs  {saved}  last: {alias.format_last_used()}",
            )

    unused_sorted = sorted((n for n, a in merged.items() if a.last_used is None), key=str)
    never_count = len(unused_sorted)
    if never_count:
        preview = ", ".join(unused_sorted[:5])
        more = " …" if never_count > 5 else ""
        table.add_row(
            f"Never used ({never_count})",
            f"{preview}{more}\n[qwik.dim]→ qwik stats --unused --prune  to remove them[/qwik.dim]",
        )

    all_rows = [
        AliasUsage(name=n, alias=a, is_overlay=n not in store.aliases) for n, a in merged.items()
    ]
    table.add_row(
        TIME_SAVED_LABEL,
        format_timedelta(estimate_time_saved(all_rows)),
    )
    if overview.busiest_group is not None:
        g = overview.busiest_group
        table.add_row(
            "Busiest group",
            f"{g.group} ({g.runs} runs across {g.aliases} aliases)",
        )
    return table
