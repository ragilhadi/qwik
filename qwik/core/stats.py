"""Usage aggregation over the alias store for ``qwik stats``.

Pure computation: reads an :class:`~qwik.core.models.AliasStore` snapshot
and derives summary figures. No new persisted state — every number here
comes from ``run_count`` / ``last_used`` already tracked on each alias.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from qwik.core.models import Alias, AliasStore

__all__ = [
    "TIME_SAVED_LABEL",
    "AliasUsage",
    "GroupUsage",
    "StatsOverview",
    "compute_overview",
    "compute_unused",
    "estimate_time_saved",
    "parse_since",
]


# Average shell-alias typing speed gain: an alias invocation replaces
# typing the full command. Assume ~40 characters per second on a keyboard
# (240 WPM is generous but aliases are short bursts of well-known text).
_CHARS_PER_SECOND: float = 4.0

TIME_SAVED_LABEL = "Time saved (estimated)"


@dataclass(frozen=True)
class AliasUsage:
    """Per-alias usage row used by all ``qwik stats`` views.

    Attributes:
        name: Alias identifier.
        alias: The alias itself.
        is_overlay: ``True`` when the alias comes from the overlay store.
    """

    name: str
    alias: Alias
    is_overlay: bool

    @property
    def run_count(self) -> int:
        """Total recorded runs for this alias."""
        return self.alias.run_count

    @property
    def chars_saved_per_run(self) -> int:
        """Rough characters an alias invocation saves versus typing it out.

        The alias name is what the user types; the expanded command is
        what they would have had to type (only counted when longer).
        """
        return max(len(self.alias.command) - len(self.name), 0)


@dataclass(frozen=True)
class GroupUsage:
    """Aggregated usage for one group.

    Attributes:
        group: Group name (never ``None``).
        runs: Sum of ``run_count`` across the group's aliases.
        aliases: Number of aliases in the group.
    """

    group: str
    runs: int
    aliases: int


def parse_since(value: str) -> timedelta:
    """Parse a human ``--since`` duration such as ``90d``, ``2w``, ``12h``.

    Args:
        value: Duration string: a positive integer followed by ``m``
            (minutes), ``h`` (hours), ``d`` (days), or ``w`` (weeks).

    Returns:
        A positive :class:`~datetime.timedelta`.

    Raises:
        ValueError: If *value* is not a supported duration expression.
    """
    stripped = value.strip().lower()
    if len(stripped) < 2:
        raise ValueError(f'Invalid --since value "{value}". Use forms like 7d, 12h, 2w.')
    suffix = stripped[-1]
    num_part = stripped[:-1]
    units: dict[str, timedelta] = {
        "m": timedelta(minutes=1),
        "h": timedelta(hours=1),
        "d": timedelta(days=1),
        "w": timedelta(weeks=1),
    }
    if suffix not in units or not num_part.isdigit():
        raise ValueError(f'Invalid --since value "{value}". Use forms like 7d, 12h, 2w.')
    if int(num_part) <= 0:
        raise ValueError(f'Invalid --since value "{value}": duration must be positive.')
    return int(num_part) * units[suffix]


def _usage_rows(store: AliasStore) -> list[AliasUsage]:
    """Build usage rows for the merged alias view (user overrides overlay)."""
    merged = store.all_aliases()
    return [
        AliasUsage(name=name, alias=alias, is_overlay=name not in store.aliases)
        for name, alias in merged.items()
    ]


def compute_overview(
    store: AliasStore,
    *,
    since: timedelta | None = None,
    now: datetime | None = None,
) -> StatsOverview:
    """Aggregate the full usage picture for the overview output.

    Args:
        store: The alias database (merged view is used).
        since: Optional window; when set, recency ("used this week"-style
            counters) counts only aliases whose ``last_used`` falls inside
            the window.
        now: Override the current time (tests).

    Returns:
        A populated :class:`StatsOverview`.
    """
    now = now or datetime.now(UTC)
    rows = _usage_rows(store)
    runs_by_group: dict[str, GroupUsage] = {}
    for row in rows:
        # Un-grouped aliases feed the total runs but never win "busiest
        # group" — the line is meaningless without a group name.
        if row.alias.group is None:
            continue
        existing = runs_by_group.get(row.alias.group)
        if existing is None:
            runs_by_group[row.alias.group] = GroupUsage(
                group=row.alias.group, runs=row.run_count, aliases=1
            )
        else:
            runs_by_group[row.alias.group] = GroupUsage(
                group=row.alias.group,
                runs=existing.runs + row.run_count,
                aliases=existing.aliases + 1,
            )

    if since is not None:
        recent_window = now - since
    else:
        recent_window = now - timedelta(days=7)
    recent = sum(
        1 for r in rows if r.alias.last_used is not None and r.alias.last_used >= recent_window
    )

    busiest = max(runs_by_group.values(), key=lambda g: (g.runs, g.aliases), default=None)

    return StatsOverview(
        total_aliases=len(rows),
        overlay_aliases=sum(1 for r in rows if r.is_overlay),
        total_runs=sum(r.run_count for r in rows),
        recent_used=recent,
        recent_window=recent_window,
        groups=sorted(runs_by_group.values(), key=lambda g: (-g.runs, g.group)),
        busiest_group=busiest,
    )


def compute_top(store: AliasStore, n: int) -> list[AliasUsage]:
    """Return the ``n`` most-used aliases, ties broken by name.

    Args:
        store: The alias database.
        n: How many entries to return; non-positive yields an empty list.

    Returns:
        Usage rows sorted by descending ``run_count``.
    """
    if n <= 0:
        return []
    rows = _usage_rows(store)
    return sorted(rows, key=lambda r: (-r.run_count, r.name))[:n]


def compute_unused(
    store: AliasStore,
    *,
    since: timedelta | None = None,
    now: datetime | None = None,
) -> list[AliasUsage]:
    """Return aliases never run, or not run within the ``--since`` window.

    Overlay aliases are included (they are part of the merged view) so
    the user sees the full picture; pruning overlays is rejected later
    because they are read-only.

    Args:
        store: The alias database.
        since: Optional window (default: never-used only).
        now: Override the current time (tests).

    Returns:
        Usage rows that qualify as unused.
    """
    now = now or datetime.now(UTC)
    if since is not None:
        cutoff = now - since
        return sorted(
            (
                r
                for r in _usage_rows(store)
                if r.alias.last_used is None or r.alias.last_used < cutoff
            ),
            key=lambda r: r.name,
        )
    return sorted(
        (r for r in _usage_rows(store) if r.alias.last_used is None),
        key=lambda r: r.name,
    )


def estimate_time_saved(rows: list[AliasUsage]) -> timedelta:
    """Rough "time saved" estimate: chars saved x runs / typing speed.

    Deliberately rough and labelled as an estimate in the output; it
    ignores think time, typo cost, and lookup time for forgotten commands.

    Args:
        rows: The usage rows to sum over.

    Returns:
        The estimated :class:`~datetime.timedelta`.
    """
    chars = sum(r.chars_saved_per_run * r.run_count for r in rows)
    seconds = chars / _CHARS_PER_SECOND
    return timedelta(seconds=seconds)


def format_timedelta(td: timedelta) -> str:
    """Format a duration compactly, e.g. ``~4 h 12 min`` or ``~35 s``.

    Args:
        td: The duration.

    Returns:
        A human string prefixed with ``~`` (estimate marker).
    """
    total = int(td.total_seconds())
    if total <= 0:
        return "~0 min"
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours} h")
    if minutes:
        parts.append(f"{minutes} min")
    if not parts:
        parts.append(f"{seconds} s")
    return "~" + " ".join(parts)


@dataclass(frozen=True)
class StatsOverview:
    """Everything the overview needs, computed once.

    Attributes:
        total_aliases: Number of aliases in the merged view.
        overlay_aliases: How many of those are overlay aliases.
        total_runs: Sum of ``run_count`` across all aliases.
        recent_used: Aliases used inside the recency window.
        recent_window: Start of the recency window (last 7 days by default).
        groups: Group aggregates sorted by descending runs.
        busiest_group: The :class:`GroupUsage` with the most runs.
    """

    total_aliases: int
    overlay_aliases: int
    total_runs: int
    recent_used: int
    recent_window: datetime
    groups: list[GroupUsage]
    busiest_group: GroupUsage | None
