"""Suggestion engine for ``qwik suggest``.

Pure computation over parsed :class:`~qwik.core.history.HistoryEntry`
records: normalize commands, count frequencies, rank candidates by
estimated keystrokes saved, and generate candidate alias names — always
passed through the conflict checker so a suggestion never proposes a
builtin or an existing alias name.

No I/O and no network: callers hand in entries and the current store.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import timedelta

from qwik.core.conflicts import ConflictChecker
from qwik.core.history import HistoryEntry
from qwik.core.models import AliasStore
from qwik.core.redact import contains_secret
from qwik.core.stats import format_timedelta

__all__ = [
    "Suggestion",
    "analyze_history",
    "generate_name",
    "is_aliasable",
    "normalize_command",
]

# Typical typing speed used for the "time saved" estimate (~40 chars/s,
# consistent with qwik.core.stats' estimate).
_CHARS_PER_SECOND = 4.0

# Commands that are not sensibly aliasable, whatever their frequency.
_NOT_ALIASABLE_FIRST_WORDS = frozenset(
    {
        "cd",  # trivial to type; aliasing it surprises people
        "exit",
        "clear",
        "history",
        "which",
        "man",
        "type",
        "qwik",  # qwik's own subcommands
    }
)

# Structural noise: commands containing any of these shapes are one-shot
# (long absolute paths, UUIDs, hashes) and make poor alias candidates.
_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_LONG_PATH_RE = re.compile(r"(?:^|\s)/(?:[\w.-]+/){3,}")
_HASH_RE = re.compile(r"\b[0-9a-fA-F]{32,}\b")
_SHELL_JOBS_RE = re.compile(r"(?:&&|\|\||;|\||&>|\$\(|`)")


def normalize_command(command: str) -> str:
    """Strip variable leading parts from a raw command line.

    ``git status --short`` and ``git status`` stay distinct candidates —
    flags are part of the command's *shape* and are kept. Two normal-
    ization rules:

    - leading env-var assignments (``FOO=bar cmd``) are dropped, since
      they make the same command hash differently across invocations
    - everything else is kept verbatim (whitespace-normalized)

    Deliberately conservative: over-grouping would suggest an alias
    whose expansion doesn't match what the user actually runs.

    Args:
        command: The raw command line.

    Returns:
        The normalized candidate core (may be empty).
    """
    words = command.split()
    if not words:
        return ""
    core: list[str] = []
    for word in words:
        if not core and "=" in word and re.match(r"^[A-Za-z_]\w*=", word):
            continue  # leading env assignment
        core.append(word)
    return " ".join(core)


def is_aliasable(normalized: str) -> bool:
    """Heuristics: would an alias for this normalized command make sense?"""
    words = normalized.split()
    if len(words) < 2:
        # Single-word commands with no args are already short.
        return False
    first = words[0]
    if first in _NOT_ALIASABLE_FIRST_WORDS:
        return False
    if _UUID_RE.search(normalized):
        return False
    if _LONG_PATH_RE.search(normalized):
        return False
    if _HASH_RE.search(normalized):
        return False
    if _SHELL_JOBS_RE.search(normalized):
        return False
    return True


def generate_name(command: str) -> str:
    """Generate a candidate alias name: initials of the command words.

    ``git status`` → ``gs``; ``docker compose up`` → ``dcu``.

    Args:
        command: The normalized command.

    Returns:
        A lowercase name candidate (possibly empty); validity is the
        ConflictChecker's job.
    """
    words = [w for w in command.split() if w]
    return "".join(w[0] for w in words if w).lower()


def _extend_on_collision(base: str, taken: set[str], command: str) -> str:
    """Extend the initials with more characters until unique.

    ``git status`` and ``git switch`` both want ``gs`` — the collision
    is broken by extending the *first* word's contribution one character
    at a time (``git status`` keeps ``gs``; a colliding ``git switch``
    becomes ``gis``→ wait: extending the first word gives ``gi`` + ``s``
    etc.), deterministically by command content, not insertion order.
    """
    if base not in taken:
        return base
    words = [w for w in command.split() if w]
    if words:
        for take in range(2, min(len(words[0]), 4) + 1):
            candidate = (words[0][:take] + "".join(w[0] for w in words[1:])).lower()
            if candidate not in taken:
                return candidate
    # Fall back to numbered suffixes.
    i = 2
    while f"{base}{i}" in taken:
        i += 1
    return f"{base}{i}"


@dataclass(frozen=True)
class Suggestion:
    """One ranked alias suggestion.

    Attributes:
        command: The normalized command core.
        count: How many times it appeared in history.
        alias: The proposed (conflict-checked) alias name.
        saved_chars: Estimated characters saved per invocation.
        redacted: ``True`` when the raw command was secret-shaped and is
            never displayed.
    """

    command: str
    count: int
    alias: str
    saved_chars: int
    redacted: bool = False

    @property
    def score(self) -> int:
        """Estimated total keystrokes saved: count x per-run savings."""
        return self.count * self.saved_chars

    @property
    def time_saved_display(self) -> str:
        """Human string like ``~52 min`` for the estimated total saved."""
        seconds = self.score / _CHARS_PER_SECOND
        return format_timedelta(timedelta(seconds=seconds))


@dataclass
class _Candidate:
    """Internal accumulation bucket for one normalized command."""

    normalized: str
    count: int = 0
    redacted: bool = False
    raw_example: str = ""
    timestamps: list[object] = field(default_factory=list)


def _accumulate(entries: list[HistoryEntry]) -> dict[str, _Candidate]:
    """Bucket history entries by normalized command, skipping noise.

    Secret-shaped commands are excluded entirely (never suggested, never
    shown), as are commands that fail the aliasability heuristics.
    """
    buckets: dict[str, _Candidate] = {}
    for entry in entries:
        if contains_secret(entry.command):
            continue  # excluded entirely — never suggested, never shown
        normalized = normalize_command(entry.command)
        if not normalized or not is_aliasable(normalized):
            continue
        bucket = buckets.setdefault(normalized, _Candidate(normalized=normalized))
        bucket.count += 1
        if entry.timestamp is not None:
            bucket.timestamps.append(entry.timestamp)
    return buckets


def _finalize_suggestions(
    buckets: dict[str, _Candidate],
    taken: set[str],
    store: AliasStore,
    checker: ConflictChecker,
    *,
    shell: str | None,
    min_count: int,
) -> list[Suggestion]:
    """Turn frequent buckets into ranked, conflict-checked suggestions."""
    suggestions: list[Suggestion] = []
    for bucket in buckets.values():
        if bucket.count < min_count:
            continue
        if normalized_has_alias(bucket.normalized, store):
            continue
        base = generate_name(bucket.normalized)
        if not base:
            continue
        name = _extend_on_collision(base, taken, bucket.normalized)
        # Conflict gate: never propose a builtin, an existing alias, or
        # (as a hard warning) a PATH binary.
        result = checker.check(name, shell=shell)
        if not result.is_safe:
            continue
        taken.add(name)
        saved = max(len(bucket.normalized) - len(name), 0)
        if saved <= 0:
            continue
        suggestions.append(
            Suggestion(
                command=bucket.normalized,
                count=bucket.count,
                alias=name,
                saved_chars=saved,
            )
        )
    return suggestions


def analyze_history(
    entries: list[HistoryEntry],
    store: AliasStore,
    *,
    shell: str | None = None,
    min_count: int = 3,
    limit: int = 10,
    checker: ConflictChecker | None = None,
) -> list[Suggestion]:
    """Turn raw history entries into ranked, conflict-checked suggestions.

    Args:
        entries: Parsed history records (any shell).
        store: The live alias store — existing aliases and (via the
            ConflictChecker) builtins/PATH binaries are excluded.
        shell: Shell used for the builtin sets in conflict checks.
        min_count: Only commands seen at least this often are considered.
        limit: Maximum number of suggestions to return.
        checker: Optional pre-built ConflictChecker (tests).

    Returns:
        Suggestions sorted by estimated keystrokes saved, descending.
        Secret-shaped commands are redacted: they get no alias name and
        are counted only as redacted rows for the summary — actually
        they are excluded entirely, per the privacy requirement.
    """
    checker = checker or ConflictChecker(store)
    taken: set[str] = set(store.aliases) | set(store.overlay_aliases)
    buckets = _accumulate(entries)
    suggestions = _finalize_suggestions(
        buckets, taken, store, checker, shell=shell, min_count=min_count
    )

    suggestions.sort(key=lambda s: (-s.score, s.command))
    return suggestions[:limit]


def normalized_has_alias(normalized: str, store: AliasStore) -> bool:
    """Return ``True`` when the exact command already has an alias.

    Both directions compare the *command string* (not the name): a user
    who already aliased ``git status`` never sees ``git status``
    suggested again. Whitespace-normalized comparison.
    """
    target = " ".join(normalized.split())
    return any(" ".join(alias.command.split()) == target for alias in store.all_aliases().values())
