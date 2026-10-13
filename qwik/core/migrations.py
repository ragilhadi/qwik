"""Forward-only schema migration for the alias store.

Migrations transform the raw dict read from ``aliases.toml`` *before* it
is handed to :class:`qwik.core.models.AliasStore.model_validate`.  This
keeps the Pydantic ``extra="forbid"`` guarantee intact while still
allowing older files to be loaded.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

__all__ = [
    "LATEST_VERSION",
    "migrate",
    "migrator",
]

LATEST_VERSION: int = 2

_Migration = Callable[[dict[str, Any]], dict[str, Any]]

_MIGRATORS: dict[int, _Migration] = {}


def migrator(from_version: int) -> Callable[[_Migration], _Migration]:
    """Register a migration from *from_version* to ``from_version + 1``.

    The decorated callable receives a dict in the *from_version* shape and
    must return a dict in the *from_version + 1* shape, setting
    ``data["version"] = from_version + 1``.
    """

    def decorator(fn: _Migration) -> _Migration:
        _MIGRATORS[from_version] = fn
        return fn

    return decorator


def migrate(data: dict[str, Any]) -> dict[str, Any]:
    """Apply registered migrations to *data* in order.

    Missing ``version`` is treated as ``0``.  A file newer than
    :data:`LATEST_VERSION` raises :class:`RuntimeError` with an
    actionable message.
    """
    v = data.get("version", 0)
    if not isinstance(v, int):
        raise RuntimeError(
            f"Store version {v!r} is not a valid integer. "
            f"Run `qwik doctor` to diagnose or restore from backup."
        )
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


@migrator(1)
def _v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """v1 → v2 identity migration: introduce platform-conditional variants.

    v2 adds optional ``command_<platform>[_<shell>]`` keys alongside each
    ``command``.  The v1 shape is unchanged and variant keys are optional,
    so no data transformation is needed — the bump only records that this
    store may carry variants, letting an older qwik refuse the file cleanly
    via the version gate instead of tripping over unknown keys.
    """
    data["version"] = 2
    return data
