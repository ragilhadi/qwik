"""Argument substitution engine for alias templates."""

from __future__ import annotations

import re
import shlex
from typing import Sequence

__all__ = [
    "expand",
    "has_placeholders",
    "validate_placeholders",
]

# Regex matching supported placeholders:
#   {1}, {2}, ..., {@}, {*}, {1:-default}
_PLACEHOLDER_RE: re.Pattern[str] = re.compile(r"\{(?:(\d+)|(@)|(\*)|(\d+):-([^}]*))\}")


def has_placeholders(command: str) -> bool:
    """Return ``True`` if *command* contains any substitution placeholders.

    Args:
        command: The alias command string.

    Returns:
        Boolean indicating template mode vs append mode.
    """
    return _PLACEHOLDER_RE.search(command) is not None


def validate_placeholders(command: str, args: Sequence[str]) -> None:
    """Raise :class:`ValueError` if a referenced positional arg is missing.

    Args:
        command: The alias command string.
        args: Positional arguments provided at runtime.

    Raises:
        ValueError: If the command references ``{N}`` where *N* is greater
            than the number of supplied *args*.
    """
    for match in _PLACEHOLDER_RE.finditer(command):
        # match groups: (digit) | (@) | (*) | (digit, default)
        if match.group(1) is not None:
            idx = int(match.group(1))
            if idx < 1:
                raise ValueError(
                    f'Invalid placeholder {{{idx}}} in alias: "{command}". '
                    f"Positional placeholders must be 1-based ({{1}}, {{2}}, ...)."
                )
            if idx > len(args):
                raise ValueError(
                    f'Missing argument {idx} for alias: "{command}" '
                    f"(received {len(args)} argument(s))"
                )
        elif match.group(4) is not None:
            idx = int(match.group(4))
            if idx < 1:
                raise ValueError(
                    f'Invalid placeholder {{{idx}}} in alias: "{command}". '
                    f"Positional placeholders must be 1-based ({{1}}, {{2}}, ...)."
                )
        # {@} and {*} are always valid regardless of args


def expand(command: str, args: Sequence[str]) -> str:
    """Expand *command* using the provided positional *args*.

    When *command* contains no placeholders the behaviour is **append**
    mode: *args* are shell-quoted and appended to the command.

    When placeholders are present the behaviour is **template** mode:
    each placeholder is replaced inline and any surplus *args* are
    appended.

    Supported placeholders:

    +------------------+------------------------------------------+
    | Placeholder      | Meaning                                  |
    +==================+==========================================+
    | ``{1}``, ``{2}`` | N-th positional argument (1-based).      |
    +------------------+------------------------------------------+
    | ``{@}``          | All arguments joined with spaces.        |
    +------------------+------------------------------------------+
    | ``{*}``          | All arguments as a single quoted string. |
    +------------------+------------------------------------------+
    | ``{1:-val}``     | N-th arg, falling back to *val* if missing.|
    +------------------+------------------------------------------+

    Args:
        command: The raw alias command.
        args: Runtime positional arguments.

    Returns:
        The fully expanded shell command.

    Raises:
        ValueError: If a required positional placeholder is missing.
    """
    if not has_placeholders(command):
        if not args:
            return command
        quoted = " ".join(shlex.quote(a) for a in args)
        return f"{command} {quoted}"

    validate_placeholders(command, args)

    def _replacer(match: re.Match[str]) -> str:
        # {N}
        if match.group(1) is not None:
            idx = int(match.group(1))
            if idx < 1:
                raise ValueError(
                    f"Invalid placeholder {{{idx}}} in alias. "
                    f"Positional placeholders must be 1-based ({{1}}, {{2}}, ...)."
                )
            return args[idx - 1] if idx <= len(args) else ""
        # {@}
        if match.group(2) is not None:
            return " ".join(args)
        # {*}
        if match.group(3) is not None:
            return shlex.quote(" ".join(args))
        # {N:-default}
        if match.group(4) is not None:
            idx = int(match.group(4))
            if idx < 1:
                raise ValueError(
                    f"Invalid placeholder {{{idx}}} in alias. "
                    f"Positional placeholders must be 1-based ({{1}}, {{2}}, ...)."
                )
            default = match.group(5)
            return args[idx - 1] if idx <= len(args) else default
        return match.group(0)

    expanded = _PLACEHOLDER_RE.sub(_replacer, command)

    # Append any surplus arguments after template substitution.
    max_ref = 0
    has_all_placeholder = False
    for m in _PLACEHOLDER_RE.finditer(command):
        if m.group(1) is not None:
            max_ref = max(max_ref, int(m.group(1)))
        elif m.group(4) is not None:
            max_ref = max(max_ref, int(m.group(4)))
        elif m.group(2) is not None or m.group(3) is not None:
            has_all_placeholder = True

    if has_all_placeholder:
        surplus: list[str] = []
    else:
        surplus = args[max_ref:]
    if surplus:
        quoted = " ".join(shlex.quote(a) for a in surplus)
        expanded = f"{expanded} {quoted}"

    return expanded
