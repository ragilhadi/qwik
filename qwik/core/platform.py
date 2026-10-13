"""Platform detection and validation for platform-conditional aliases.

The alias store may carry per-platform command variants (``command_macos``)
and per-shell variants (``command_windows_pwsh``).  This module normalises
``sys.platform`` onto the small, closed set of platform keys the store
understands, so every consumer — ``qwik run``, ``qwik init``, ``qwik show``
— resolves variants against the same three names.
"""

from __future__ import annotations

import sys

__all__ = [
    "PLATFORMS",
    "current_platform",
    "validate_platform",
    "variant_key",
]

# The closed set of platform keys recognised by the alias model.  Keys in
# the store are exactly these (``command_linux``, ``command_macos``,
# ``command_windows``) plus ``<platform>_<shell>`` refinements.
PLATFORMS: tuple[str, ...] = ("linux", "macos", "windows")


def variant_key(platform: str, shell: str | None = None) -> str:
    """Return the store key for a platform/shell command variant.

    Args:
        platform: One of :data:`PLATFORMS`.
        shell: An optional registered shell name.

    Returns:
        ``command_<platform>`` or ``command_<platform>_<shell>`` — the
        exact shape used on disk and inside ``Alias.command_variants``.
    """
    if shell is None:
        return f"command_{platform}"
    return f"command_{platform}_{shell}"


def current_platform() -> str:
    """Return the current host as one of :data:`PLATFORMS`.

    ``sys.platform`` is read at call time rather than import time so tests
    can monkeypatch it.  Windows reports ``win32`` on both CPython builds
    (32- and 64-bit), macOS reports ``darwin``, and every other platform
    qwik can plausibly run on — the BSDs and anything POSIX-shaped — is
    bucketed as ``linux`` because the platform-conditional commands that
    matter (``xdg-open`` vs ``open`` vs ``start``) all treat those hosts
    as "the Linux one".

    Returns:
        ``"linux"``, ``"macos"``, or ``"windows"``.
    """
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def validate_platform(name: str) -> str:
    """Validate and normalise a user-supplied platform name.

    Args:
        name: A platform name (case-insensitive, surrounding whitespace
            tolerated).

    Returns:
        The lowercased platform name if it is legal.

    Raises:
        ValueError: If *name* is not one of :data:`PLATFORMS`.
    """
    cleaned = name.strip().lower()
    if cleaned not in PLATFORMS:
        raise ValueError(f'Invalid platform "{name}": must be one of {", ".join(PLATFORMS)}.')
    return cleaned
