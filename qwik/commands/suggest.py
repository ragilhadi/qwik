"""``qwik suggest`` — mine shell history for alias candidates.

Reads the user's shell history, finds frequently repeated commands that
have no alias, ranks them by estimated time saved, and offers to create
aliases interactively.

Privacy: history contains secrets. This command never transmits
anything anywhere — the only I/O is reading the local history file (see
``qwik/core/history.py`` for which files, and ``--history-file`` to
override) and writing to the local alias store when the user confirms.
Secret-shaped commands are detected by :mod:`qwik.core.redact` and
excluded from suggestions entirely.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from qwik.core.conflicts import ConflictChecker
from qwik.core.history import read_history
from qwik.core.models import Alias
from qwik.core.shell_detect import detect_shell
from qwik.core.stats import parse_since
from qwik.core.store import get_store
from qwik.core.suggest import analyze_history
from qwik.ui.prompts import print_error, print_info, print_success, print_warning, prompt_text
from qwik.ui.theme import get_console

if TYPE_CHECKING:
    from rich.console import Console

    from qwik.core.store import Store
    from qwik.core.suggest import Suggestion

__all__ = ["suggest_command"]

_TABLE_WIDTH_CMD = 36


def _suggestions_to_json(suggestions: list[Suggestion]) -> list[dict[str, object]]:
    """Serialise suggestions for ``--json`` (plain values, no markup)."""
    return [
        {
            "rank": i,
            "command": s.command,
            "alias": s.alias,
            "count": s.count,
            "saved_chars_per_run": s.saved_chars,
            "score": s.score,
            "time_saved_estimate": s.time_saved_display,
        }
        for i, s in enumerate(suggestions, 1)
    ]


def _shell_for_suggest(shell: str | None) -> str:
    """Resolve the shell whose history should be read."""
    return shell or detect_shell() or "bash"


def _print_analysis_header(
    console: Console,
    total: int,
    history_display: str,
    since_display: str,
) -> None:
    window = f" (last {since_display})" if since_display != "all time" else ""
    console.print(f"Analyzed [bold]{total}[/bold] commands from {history_display}{window}")


def _print_suggestion_table(console: Console, rows: list[tuple[int, int, str, str, str]]) -> None:
    """Render the #/Count/Command/Suggested/Saves table with fixed widths."""
    console.print()
    header = (
        f"  {'#':>3}  {'Count':>5}  {'Command':<{_TABLE_WIDTH_CMD}}  "
        f"{'Suggested':<10}  {'Saves':>8}"
    )
    console.print(header)
    console.print(
        "  "
        + "─" * 3
        + "  "
        + "─" * 5
        + "  "
        + "─" * _TABLE_WIDTH_CMD
        + "  "
        + "─" * 10
        + "  "
        + "─" * 8
    )
    for rank, count, command, alias, saves in rows:
        display = (
            command if len(command) <= _TABLE_WIDTH_CMD else command[: _TABLE_WIDTH_CMD - 3] + "…"
        )
        console.print(
            f"  {rank:>3}  {count:>5}  {display:<{_TABLE_WIDTH_CMD}}  {alias:<10}  {saves:>8}"
        )


def suggest_command(
    limit: int = typer.Option(10, "--limit", "-n", min=1, help="Max candidates to review."),
    min_count: int = typer.Option(
        3, "--min-count", "-c", min=1, help="Only commands run at least N times."
    ),
    since: str | None = typer.Option(
        None, "--since", metavar="DURATION", help="Window (e.g. 30d, 2w, 12h). Default: all."
    ),
    history_file: Path | None = typer.Option(
        None,
        "--history-file",
        metavar="PATH",
        help="Override the history file location (privacy: read exactly this file).",
    ),
    shell: str | None = typer.Option(
        None, "--shell", help="Shell whose history format to parse (default: auto-detect)."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print candidates, create nothing."),
    json_output: bool = typer.Option(
        False, "--json", help="Output machine-readable JSON (no markup, no prompts)."
    ),
) -> None:
    """Mine shell history and offer to create aliases for frequent commands."""
    console = get_console()
    store = get_store()

    since_delta = None
    if since is not None:
        try:
            since_delta = parse_since(since)
        except ValueError as exc:
            print_error(str(exc), console=console)
            raise typer.Exit(1) from exc

    effective_shell = _shell_for_suggest(shell)
    entries, warnings = read_history(
        effective_shell,
        since=since_delta,
        history_file=history_file,
        now=datetime.now(UTC),
    )

    history_display = (
        str(history_file) if history_file is not None else _first_history_location(effective_shell)
    )
    since_display = _since_display(since)

    for warning in warnings:
        print_warning(warning, console=console)
        if not entries:
            print_info(
                "`qwik suggest` needs shell history to work; nothing was analyzed.",
                console=console,
            )
            raise typer.Exit(0)

    data = store.load()
    checker = ConflictChecker(data)
    suggestions = analyze_history(
        entries,
        data,
        shell=effective_shell,
        min_count=min_count,
        limit=limit,
        checker=checker,
    )

    if json_output:
        import json

        console.print_json(
            json.dumps(
                {
                    "analyzed_commands": len(entries),
                    "history_source": history_display,
                    "since": since,
                    "suggestions": _suggestions_to_json(suggestions),
                }
            )
        )
        return

    _print_analysis_header(console, len(entries), history_display, since_display)

    if not suggestions:
        console.print()
        console.print("[qwik.dim]No alias-worthy commands found.[/qwik.dim]")
        console.print(
            "[qwik.dim]Either history is sparse, or the frequent commands already "
            "have aliases.[/qwik.dim]"
        )
        return

    _print_suggestion_table(
        console,
        [
            (i, s.count, s.command, s.alias, s.time_saved_display)
            for i, s in enumerate(suggestions, 1)
        ],
    )

    if dry_run:
        console.print()
        console.print("[qwik.dim]Dry run — nothing was created.[/qwik.dim]")
        return

    console.print()
    _interactive_review(suggestions, store, console)


def _since_display(since: str | None) -> str:
    if since is None:
        return "all time"
    return since


def _first_history_location(shell: str) -> str:
    from qwik.core.history import default_history_paths

    paths = default_history_paths(shell)
    for p in paths:
        if p.is_file():
            return str(p)
    return str(paths[0]) if paths else "<unknown>"


def _interactive_review(
    suggestions: list[Suggestion],
    store: Store,
    console: Console,
) -> None:
    """Walk the ranked list; y creates, e edits the name, n skips, s stops."""
    created = 0
    for index, suggestion in enumerate(suggestions, 1):
        answer = prompt_text(
            f"Create alias for #{index} ({suggestion.alias} → {suggestion.command!r})? "
            "[y/n/e(dit)/s(kip all)]",
            default="n",
            console=console,
        )
        answer = answer.strip().lower()
        if answer in ("s", "skip"):
            break
        if answer in ("y", "yes"):
            name = suggestion.alias
        elif answer in ("e", "edit"):
            name = prompt_text(
                "? Alias name", default=suggestion.alias, console=console, allow_empty=False
            ).strip()
        else:
            continue
        try:
            _create_alias(store, name, suggestion)
        except typer.Exit:
            continue
        created += 1
        print_success(f'Added "{name}" → {suggestion.command!r}', console=console)

    if created:
        print_info(
            f"Created {created} alias{'es' if created != 1 else ''}. "
            "Run `source <rc>` or open a new terminal to use them.",
            console=console,
        )
    else:
        print_info("No aliases created.", console=console)


def _create_alias(store: Store, name: str, suggestion: Suggestion) -> None:
    """Add one alias through the same mutate path as ``qwik add``.

    Raises :class:`typer.Exit(1)` on failure so the review loop can move
    on to the next candidate.
    """
    console = get_console()
    alias = Alias(command=suggestion.command)
    try:
        with store.mutate() as fresh_data:
            fresh_data.add(name, alias)
    except KeyError as exc:
        print_error(str(exc), console=console)
        raise typer.Exit(1) from exc
    except Exception as exc:
        print_error(str(exc), console=console)
        raise typer.Exit(1) from exc
