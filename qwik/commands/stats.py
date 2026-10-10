"""``qwik stats`` — usage dashboard built on collected ``run_count`` data."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import typer

from qwik.core.stats import (
    AliasUsage,
    compute_overview,
    compute_top,
    compute_unused,
    estimate_time_saved,
    parse_since,
)
from qwik.core.store import get_store
from qwik.ui.prompts import print_error, print_success, prompt_confirm
from qwik.ui.tables import render_stats
from qwik.ui.theme import get_console

if TYPE_CHECKING:
    from rich.console import Console

__all__ = ["stats_command"]


def _validate_options(
    since: str | None,
    prune: bool,
    unused: bool,
    top: int | None,
    console: Console,
) -> timedelta | None:
    """Fail fast on bad options (before any store read); parse ``--since``."""
    since_delta = None
    if since is not None:
        try:
            since_delta = parse_since(since)
        except ValueError as exc:
            print_error(str(exc), console=console)
            raise typer.Exit(1) from exc
    if prune and not unused:
        print_error("--prune requires --unused.", console=console)
        raise typer.Exit(1)
    if top is not None and top <= 0:
        print_error("--top must be a positive number.", console=console)
        raise typer.Exit(1)
    return since_delta


def _print_empty_store(console: Console) -> None:
    console.print("[dim]No aliases yet. Run `qwik add <name> <command>` to create one.[/dim]")
    console.print("[dim]`qwik stats` will light up once you have aliases and runs.[/dim]")


def _empty_json_payload() -> dict[str, Any]:
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_aliases": 0,
        "overlay_aliases": 0,
        "total_runs": 0,
        "time_saved_estimate_seconds": 0,
        "top": [],
        "unused": [],
    }


def _emit_empty_store(console: Console) -> None:
    console.print_json(json.dumps(_empty_json_payload()))


def _emit_json_stats(
    data: Any,
    now: datetime,
    since: str | None,
    since_delta: timedelta | None,
    top: int | None,
    unused: bool,
    console: Console,
) -> None:
    """Print the ``--json`` usage dashboard for a non-empty store."""
    top_rows = compute_top(data, top) if top is not None else []
    unused_rows = compute_unused(data, since=since_delta, now=now) if unused else []
    all_rows = [
        AliasUsage(name=n, alias=a, is_overlay=n not in data.aliases)
        for n, a in data.all_aliases().items()
    ]
    payload: dict[str, Any] = {
        "generated_at": now.isoformat(),
        "total_aliases": len(all_rows),
        "overlay_aliases": sum(1 for r in all_rows if r.is_overlay),
        "total_runs": sum(r.run_count for r in all_rows),
        "time_saved_estimate_seconds": int(estimate_time_saved(all_rows).total_seconds()),
        "top": [_usage_to_json(r) for r in top_rows],
        "unused": [_usage_to_json(r) for r in unused_rows],
    }
    if since is not None:
        payload["since"] = since
    console.print_json(json.dumps(payload))


def _print_unused_view(
    data: Any,
    now: datetime,
    since_delta: timedelta | None,
    *,
    prune: bool,
    yes: bool,
    console: Console,
) -> None:
    """Render the ``--unused`` view, falling back to interactive pruning."""
    unused_rows = compute_unused(data, since=since_delta, now=now)
    if not unused_rows:
        console.print("[qwik.success]✓ No unused aliases matching that window.[/qwik.success]")
        return
    if prune:
        _prune_unused(unused_rows, yes=yes, console=console)
        return
    console.print(render_stats(data, top_rows=None, unused_rows=unused_rows, since=since_delta))


def _print_top_view(data: Any, top: int, console: Console) -> None:
    """Render the ``--top N`` view."""
    top_rows = compute_top(data, top)
    console.print(render_stats(data, top_rows=top_rows, unused_rows=None))


def _usage_to_json(row: AliasUsage) -> dict[str, Any]:
    """Serialise one usage row for ``--json`` (plain values, no markup)."""
    alias = row.alias
    return {
        "name": row.name,
        "command": alias.command,
        "overlay": row.is_overlay,
        "enabled": alias.enabled,
        "group": alias.group,
        "tags": list(alias.tag),
        "run_count": alias.run_count,
        "last_used": alias.last_used.isoformat() if alias.last_used else None,
    }


def stats_command(
    top: int | None = typer.Option(
        None,
        "--top",
        "-t",
        metavar="N",
        help="Show the N most-used aliases.",
    ),
    unused: bool = typer.Option(
        False,
        "--unused",
        help="Show aliases never run, or not run since --since.",
    ),
    since: str | None = typer.Option(
        None,
        "--since",
        metavar="DURATION",
        help="Window for --unused (e.g. 7d, 12h, 2w). Default: never used.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output machine-readable JSON (no markup).",
    ),
    prune: bool = typer.Option(
        False,
        "--prune",
        help="With --unused: remove the unused user aliases after confirmation.",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation for --prune."),
) -> None:
    """Summarise alias usage: most used, never used, time saved."""
    store = get_store()
    console = get_console()

    # Options are validated before any store read so bad --since values
    # fail fast with a clear error.
    since_delta = _validate_options(since, prune, unused, top, console)

    data = store.load()

    if not data.all_aliases():
        if json_output:
            _emit_empty_store(console)
        else:
            _print_empty_store(console)
        return

    now = datetime.now(UTC)

    if json_output:
        _emit_json_stats(data, now, since, since_delta, top, unused, console)
        return

    if unused:
        _print_unused_view(data, now, since_delta, prune=prune, yes=yes, console=console)
        return

    if top is not None:
        _print_top_view(data, top, console)
        return

    # Bare `qwik stats` overview
    overview = compute_overview(data, now=now)
    console.print(render_stats(data, overview=overview))


def _prune_unused(
    unused_rows: list[AliasUsage],
    *,
    yes: bool,
    console: Console,
) -> None:
    """Remove unused *user* aliases through the normal confirm/backup path.

    Overlay aliases are read-only and always skipped; they are reported
    as such instead.
    """
    removable = [r for r in unused_rows if not r.is_overlay]
    overlays = [r for r in unused_rows if r.is_overlay]

    if overlays:
        names = ", ".join(r.name for r in overlays)
        console.print(f"[qwik.info]ℹ Skipping overlay aliases (read-only): {names}[/qwik.info]")  # noqa: RUF001 — intentional info glyph

    if not removable:
        console.print(
            "[qwik.info]ℹ Nothing to prune — all unused aliases are read-only overlays.[/qwik.info]"  # noqa: RUF001 — intentional info glyph
        )
        return

    console.print("About to remove the following aliases:")
    for row in removable:
        console.print(f"  [qwik.highlight]{row.name}[/qwik.highlight] → {row.alias.command!r}")

    if not yes and not prompt_confirm(
        f"Remove {len(removable)} alias{'es' if len(removable) != 1 else ''}?",
        default=False,
        console=console,
    ):
        console.print("[qwik.info]ℹ Prune cancelled.[/qwik.info]")  # noqa: RUF001 — intentional info glyph
        return

    from qwik.commands.remove import remove_alias

    removed = 0
    for row in removable:
        # Re-check existence inside remove: another process may have
        # removed the alias between listing and pruning. Errors leave
        # the rest of the batch intact, matching `qwik rm` behaviour.
        try:
            remove_alias(row.name, yes=True)
            removed += 1
        except typer.Exit:
            print_error(f'Failed to remove "{row.name}".', console=console)

    if removed:
        print_success(
            f"Pruned {removed} alias{'es' if removed != 1 else ''} — a backup was written.",
            console=console,
        )
