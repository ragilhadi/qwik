"""Forward-only schema migration for the alias store.

Migrations transform the raw dict read from ``aliases.toml`` *before* it
is handed to :class:`qwik.core.models.AliasStore.model_validate`.  This
keeps the Pydantic ``extra="forbid"`` guarantee intact while still
allowing older files to be loaded.
"""

from __future__ import annotations

from typing import Any, Callable

__all__ = [
    "LATEST_VERSION",
    "migrate",
    "migrator",
]

LATEST_VERSION: int = 1

_MIGRATORS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}


def migrator(from_version: int) -> Callable[[Callable[[dict[str, Any]], dict[str, Any]]], Callable[[dict[str, Any]], dict[str, Any]]]:
    """Register a migration from *from_version* to ``from_version + 1``.

    The decorated callable receives a dict in the *from_version* shape and
    must return a dict in the *from_version + 1* shape, setting
    ``data["version"] = from_version + 1``.
    """
    def decorator(
        fn: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> Callable[[dict[str, Any]], dict[str, Any]]:
        _MIGRATORS[from_version] = fn
        return fn

    return decorator


def migrate(data: dict[str, Any]) -> dict[str, Any]:
    """Apply registered migrations to *data* in order.

    Missing ``version`` is treated as ``0``.  A file newer than
    :data:`LATEST_VERSION` raises :class:`RuntimeError` with an
    actionable message.
    """
    v: int = data.get("version", 0)
    if v > LATEST_VERSION:
        raise RuntimeError(
            f"Store version {v} is newer than supported (max {LATEST_VERSION}). "
            f"Upgrade qwik or restore from backup via 'qwik doctor'."
        )
    while v < LATEST_VERSION:
        data = _MIGRATORS[v](data)
        v = data["version"]
    return data


@migrator(0)
def _v0_to_v1(data: dict[str, Any]) -> dict[str, Any]:
    """v0 → v1 identity migration: ensure the ``version`` key is set."""
    data["version"] = 1
    return data