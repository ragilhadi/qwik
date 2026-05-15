"""Fuzzy search implementation backed by ``rapidfuzz``."""

from __future__ import annotations

from rapidfuzz import fuzz

from qwik.core.models import Alias, AliasStore

__all__ = [
    "search_aliases",
    "score_alias",
]

# Fields to scan during a search, in order of relevance.
_SEARCH_FIELDS: tuple[str, ...] = ("command", "description")


def score_alias(alias: Alias, name: str, query: str) -> float:
    """Compute a composite fuzzy match score for an alias.

    The score is a weighted combination of:

    - Name match (highest weight).
    - Tag match.
    - Command + description match.

    Args:
        alias: The alias definition.
        name: The alias identifier.
        query: The user search string.

    Returns:
        A float between ``0`` and ``100``.
    """
    name_score = fuzz.ratio(name.lower(), query.lower())
    tag_score = max(
        (fuzz.ratio(t.lower(), query.lower()) for t in alias.tag),
        default=0,
    )
    field_text = " ".join(
        getattr(alias, f, "") for f in _SEARCH_FIELDS if getattr(alias, f, "")
    )
    field_score = fuzz.ratio(field_text.lower(), query.lower())

    return name_score * 0.5 + tag_score * 0.25 + field_score * 0.25


def search_aliases(
    store: AliasStore,
    query: str,
    *,
    tag: str | None = None,
    enabled_only: bool = False,
    limit: int = 20,
) -> list[tuple[str, Alias, float]]:
    """Search aliases with optional tag filter and fuzzy ranking.

    Args:
        store: The alias database.
        query: Free-text search string.
        tag: If provided, restrict results to aliases containing this tag.
        enabled_only: If ``True``, exclude disabled aliases.
        limit: Maximum number of results to return.

    Returns:
        A list of ``(name, alias, score)`` tuples sorted by descending
        score.
    """
    candidates: list[tuple[str, Alias]] = []
    for name, alias in store.aliases.items():
        if enabled_only and not alias.enabled:
            continue
        if tag is not None and tag not in alias.tag:
            continue
        candidates.append((name, alias))

    if not query:
        # No query → return all candidates alphabetically with dummy score.
        return [(n, a, 0.0) for n, a in sorted(candidates)]

    scored: list[tuple[str, Alias, float]] = []
    for name, alias in candidates:
        scored.append((name, alias, score_alias(alias, name, query)))

    scored.sort(key=lambda t: t[2], reverse=True)
    return scored[:limit]
