"""Structural diff between two alias stores.

Pure computation over :class:`~qwik.core.models.AliasStore` snapshots —
no filesystem access, no locking. Reused by ``qwik undo`` (what would a
restore change?), the overlay update preview, and ``import --overwrite``.
"""

from __future__ import annotations

from dataclasses import dataclass

from qwik.core.models import AliasStore

__all__ = [
    "DiffEntry",
    "StoreDiff",
    "diff_stores",
]


@dataclass(frozen=True)
class DiffEntry:
    """One alias-level difference between two stores.

    Attributes:
        name: Alias identifier.
        old_command: Command in the "from" store (``None`` when added).
        new_command: Command in the "to" store (``None`` when removed).
    """

    name: str
    old_command: str | None
    new_command: str | None

    @property
    def kind(self) -> str:
        """Return ``"add"``, ``"remove"``, or ``"change"``."""
        if self.old_command is None:
            return "add"
        if self.new_command is None:
            return "remove"
        return "change"


def diff_stores(a: AliasStore, b: AliasStore) -> StoreDiff:
    """Compare two stores and classify every alias difference.

    Args:
        a: The "from" store (e.g. a backup).
        b: The "to" store (e.g. the live store).

    Returns:
        A :class:`StoreDiff` with sorted added / removed / changed lists.
        Two aliases with the same name but different commands count as
        changed; identical commands are not reported.
    """
    a_names = set(a.aliases)
    b_names = set(b.aliases)

    added = tuple(
        DiffEntry(name=n, old_command=None, new_command=b.aliases[n].command)
        for n in sorted(b_names - a_names)
    )
    removed = tuple(
        DiffEntry(name=n, old_command=a.aliases[n].command, new_command=None)
        for n in sorted(a_names - b_names)
    )
    changed = tuple(
        DiffEntry(name=n, old_command=a.aliases[n].command, new_command=b.aliases[n].command)
        for n in sorted(a_names & b_names)
        if a.aliases[n].command != b.aliases[n].command
    )
    return StoreDiff(added=added, removed=removed, changed=changed)


@dataclass(frozen=True)
class StoreDiff:
    """Result of :func:`diff_stores`.

    Attributes:
        added: Aliases present in ``b`` but not in ``a``.
        removed: Aliases present in ``a`` but not in ``b``.
        changed: Aliases in both whose commands differ.
    """

    added: tuple[DiffEntry, ...] = ()
    removed: tuple[DiffEntry, ...] = ()
    changed: tuple[DiffEntry, ...] = ()

    @property
    def empty(self) -> bool:
        """Return ``True`` when there is no difference at all."""
        return not (self.added or self.removed or self.changed)
