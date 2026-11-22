"""Shared parsing for ``--complete-with`` / ``--complete-from`` options.

Used by ``qwik add`` and ``qwik edit``; kept here so both commands agree
on the key grammar and validation errors.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from rich.console import Console

from qwik.ui.prompts import print_error
from qwik.ui.theme import get_console

__all__ = ["build_complete_map"]

_POS_OR_NAME = re.compile(r"\{(\d+)(?::-[^}]*)?\}|\{([A-Za-z_][A-Za-z0-9_-]*)(?::-[^}]*)?\}")


def build_complete_map(
    name: str,
    command: str,
    complete_with: Sequence[str] | None,
    console: Console | None = None,
) -> dict[str, str]:
    """Parse ``--complete-with KEY="COMMAND"`` entries into a ``complete`` map.

    KEY is a positional index (``1``, ``2``, …) or a named placeholder
    (``branch``); the value is the shell command whose output supplies the
    candidates.  Exits with code 1 (via :func:`print_error`) when the
    entry grammar is wrong or KEY doesn't reference a real argument
    position of *command*.
    """
    if not complete_with:
        return {}
    console = console or get_console()

    # Named placeholders resolve in first-appearance order, mirroring the
    # substitution engine's runtime name map.
    name_to_index: dict[str, int] = {}
    highest = 0
    for match in _POS_OR_NAME.finditer(command):
        if match.group(1) is not None:
            highest = max(highest, int(match.group(1)))
        else:
            highest += 1
            name_to_index[match.group(2)] = highest

    result: dict[str, str] = {}
    for entry in complete_with:
        key, sep, value = entry.partition("=")
        if not sep or not key.strip() or not value:
            print_error(
                f'Invalid --complete-with entry "{entry}".',
                suggestion='Expected KEY="COMMAND", e.g.'
                " --complete-with branch=\"git branch --format='%(refname:short)'\"",
                console=console,
            )
            raise SystemExit(1)
        key = key.strip()
        if key.isdigit():
            if not (1 <= int(key) <= highest):
                print_error(
                    f'--complete-with {key}: alias "{name}" has no argument'
                    f" {key} (its template consumes {highest} positional"
                    " placeholder(s)).",
                    console=console,
                )
                raise SystemExit(1)
            slot = key
        elif key in name_to_index:
            slot = key
        else:
            print_error(
                f'--complete-with {key}: name "{key}" is not a placeholder of alias "{name}".',
                suggestion=(
                    "Named placeholders found in the command:"
                    f" {sorted(name_to_index) or 'none'};"
                    " positional keys 1.."
                    f"{highest or 'none'}."
                ),
                console=console,
            )
            raise SystemExit(1)
        if slot in result:
            print_error(
                f"--complete-with {key}: that argument already has a completion.",
                console=console,
            )
            raise SystemExit(1)
        result[slot] = value

    return result
