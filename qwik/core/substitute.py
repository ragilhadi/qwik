"""Argument substitution engine for alias templates."""

from __future__ import annotations

import re
import shlex
from typing import Sequence

__all__ = [
    "expand",
    "find_unrecognized_braces",
    "has_placeholders",
    "quote_for_shell",
    "validate_placeholders",
    "validate_placeholders_static",
]

# cmd.exe interprets these even inside a quoted argument unless each is
# individually caret-escaped.
_CMD_METACHARACTERS = frozenset("&|<>^()%!")


def _quote_cmd(value: str) -> str:
    """Quote *value* as one literal cmd.exe/doskey argument.

    cmd.exe has no single quoting convention that makes a string fully
    opaque the way POSIX single quotes do: metacharacters are still live
    even inside a double-quoted argument, so they must be caret-escaped
    individually, and the whole thing is then wrapped in doubled double
    quotes so the target program's own CRT argv parser treats it as one
    argument.

    Args:
        value: The raw argument value.

    Returns:
        The quoted string, safe to splice into a cmd.exe command line.
    """
    if not value:
        return '""'
    out: list[str] = []
    for ch in value:
        if ch in _CMD_METACHARACTERS:
            out.append("^" + ch)
        elif ch == '"':
            out.append('""')
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def _quote_pwsh(value: str) -> str:
    """Quote *value* as a PowerShell single-quoted string literal.

    PowerShell single-quoted strings perform no variable or subexpression
    expansion at all — unlike POSIX, ``$var`` inside one stays literal —
    so the only character that needs escaping is an embedded ``'``,
    doubled per PowerShell's own convention.

    Args:
        value: The raw argument value.

    Returns:
        The quoted string, safe to splice into a PowerShell command line.
    """
    return "'" + value.replace("'", "''") + "'"


def quote_for_shell(value: str, shell: str | None) -> str:
    """Quote *value* as one literal argument for *shell*'s parsing rules.

    ``shlex.quote`` (POSIX single-quote syntax) is only meaningful to
    ``sh``/``bash``/``zsh``/``fish`` — it means nothing to ``cmd.exe``,
    and PowerShell has its own escaping convention. The right quoting
    therefore depends on which shell will actually execute the expanded
    string, not on the host platform: a user can be running POSIX bash
    under Git Bash or WSL on a Windows host.

    Args:
        value: The raw argument value.
        shell: The target shell name (e.g. ``"cmd"``, ``"pwsh"``,
            ``"bash"``), or ``None`` to fall back to POSIX quoting.

    Returns:
        The quoted string.
    """
    if shell == "cmd":
        return _quote_cmd(value)
    if shell == "pwsh":
        return _quote_pwsh(value)
    return shlex.quote(value)

_NAMED_RE = r"[A-Za-z_][A-Za-z0-9_-]*"
_PLACEHOLDER_RE: re.Pattern[str] = re.compile(
    r"\{(?:(\d+)|(@)|(\*)|(\d+):-([^}]*)|(" + _NAMED_RE + r")|(" + _NAMED_RE + r"):-([^}]*))\}"
)
_BRACE_SPAN_RE: re.Pattern[str] = re.compile(r"\{[^{}]*\}")


def has_placeholders(command: str) -> bool:
    """Return ``True`` if *command* contains any substitution placeholders.

    Args:
        command: The alias command string.

    Returns:
        Boolean indicating template mode vs append mode.
    """
    return _PLACEHOLDER_RE.search(command) is not None


def _named_placeholder_index_map(command: str) -> dict[str, int]:
    """Return a mapping of named-placeholder names to 1-based positional indices.

    Names are assigned indices by the order of their first appearance in
    *command*, left-to-right. Numeric placeholders (``{N}``, ``{N:-default}``)
    consume index slots too, so a name appearing after ``{1}`` gets index 2.

    Args:
        command: The alias command string.

    Returns:
        A dict mapping each named-placeholder name to its 1-based index.
        Empty if *command* has no named placeholders.
    """
    name_to_index: dict[str, int] = {}
    next_index = 1
    for match in _PLACEHOLDER_RE.finditer(command):
        name = match.group(6) or match.group(7)
        if name is not None:
            if name not in name_to_index:
                name_to_index[name] = next_index
                next_index += 1
        else:
            if match.group(1) is not None or match.group(4) is not None:
                next_index += 1
    return name_to_index


def validate_placeholders_static(command: str) -> None:
    """Reject structurally-invalid placeholders without runtime args.

    Two rejection paths:

    1. Numeric placeholders ``{0}`` / negative indices (1-based requirement).
    2. ``{...}`` spans that *look like a placeholder attempt* but fail the
       ``_PLACEHOLDER_RE`` grammar. See :func:`find_unrecognized_braces` for
       the heuristic that distinguishes attempts from literal braces.

    Args:
        command: The alias command to check.

    Raises:
        ValueError: If any placeholder is structurally invalid. The message
            names the first offending token.
    """
    for match in _PLACEHOLDER_RE.finditer(command):
        for gidx in (1, 4):
            if match.group(gidx) is not None:
                idx = int(match.group(gidx))
                if idx < 1:
                    raise ValueError(
                        f'Invalid placeholder {{{idx}}} in alias: "{command}". '
                        f"Positional placeholders must be 1-based ({{1}}, {{2}}, ...)."
                    )

    unrecognized = find_unrecognized_braces(command)
    if unrecognized:
        token = unrecognized[0]
        raise ValueError(
            f'Malformed placeholder {token!r} in alias: "{command}". '
            f"Use {{N}}, {{@}}, {{*}}, {{N:-default}}, {{name}}, or "
            f"{{name:-default}}."
        )


def find_unrecognized_braces(command: str) -> list[str]:
    """Return ``{...}`` spans that look like placeholder attempts but
    fail the ``_PLACEHOLDER_RE`` grammar.

    A ``{...}`` span (a ``{`` immediately followed by a matching ``}`` with
    no nested braces in between) is considered a *placeholder attempt* and
    therefore rejected when any of the following hold:

    - its inner text contains ``:-`` (the default separator),
    - its inner text contains ``@`` or ``*`` (special placeholders), or
    - its inner text starts with an ASCII letter, digit, or underscore
      (a name or numeric index would start with one of these).

    Spans that do not meet any of the above (e.g. ``{}``, ``{ }``,
    ``{$$$}``) are left as literal text — the user most likely intended a
    literal brace pair. Unclosed ``{`` (no matching ``}``) is also left
    literal.

    Spans matched by ``_PLACEHOLDER_RE`` are always skipped (they are
    valid placeholders). Each ``{...}`` span matched by ``_BRACE_SPAN_RE``
    that does not overlap a valid placeholder match is checked against the
    heuristic above.

    Args:
        command: The alias command string to scan.

    Returns:
        A list of offending ``{...}`` token strings, in order of
        appearance. Empty when the command has no malformed placeholder
        attempts.
    """
    valid_spans = [
        (m.start(), m.end()) for m in _PLACEHOLDER_RE.finditer(command)
    ]

    def _overlaps_valid(start: int, end: int) -> bool:
        for vs, ve in valid_spans:
            if start < ve and vs < end:
                return True
        return False

    offenders: list[str] = []
    for m in _BRACE_SPAN_RE.finditer(command):
        if _overlaps_valid(m.start(), m.end()):
            continue
        inner = m.group(0)[1:-1]
        if (
            ":-" in inner
            or "@" in inner
            or "*" in inner
            or (inner[:1].isascii() and (inner[:1].isalnum() or inner[:1] == "_"))
        ):
            offenders.append(m.group(0))
    return offenders


def _raise_invalid_index(idx: int, command: str) -> None:
    """Raise ValueError for a 0/negative positional placeholder."""
    raise ValueError(
        f'Invalid placeholder {{{idx}}} in alias: "{command}". '
        f"Positional placeholders must be 1-based ({{1}}, {{2}}, ...)."
    )


def validate_placeholders(command: str, args: Sequence[str]) -> None:
    """Raise :class:`ValueError` if a referenced positional arg is missing.

    Args:
        command: The alias command string.
        args: Positional arguments provided at runtime.

    Raises:
        ValueError: If the command references ``{N}`` where *N* is greater
            than the number of supplied *args*.
    """
    name_map = _named_placeholder_index_map(command)
    for match in _PLACEHOLDER_RE.finditer(command):
        if match.group(1) is not None:
            idx = int(match.group(1))
            if idx < 1:
                _raise_invalid_index(idx, command)
            if idx > len(args):
                raise ValueError(
                    f'Missing argument {idx} for alias: "{command}" '
                    f"(received {len(args)} argument(s))"
                )
        elif match.group(4) is not None:
            idx = int(match.group(4))
            if idx < 1:
                _raise_invalid_index(idx, command)
        elif match.group(6) is not None:
            name = match.group(6)
            idx = name_map[name]
            if idx > len(args):
                raise ValueError(
                    f'Missing argument for placeholder {{{name}}} '
                    f'(position {idx}) in alias: "{command}" '
                    f"(received {len(args)} argument(s))"
                )
        elif match.group(7) is not None:
            pass


def _parse_positional(
    match: re.Match[str], args: Sequence[str], command: str, shell: str | None
) -> str:
    """Handle {N} and {N:-default} placeholders."""
    if match.group(1) is not None:
        idx = int(match.group(1))
        if idx < 1:
            _raise_invalid_index(idx, command)
        return quote_for_shell(args[idx - 1], shell) if idx <= len(args) else ""
    if match.group(4) is not None:
        idx = int(match.group(4))
        if idx < 1:
            _raise_invalid_index(idx, command)
        value = args[idx - 1] if idx <= len(args) else match.group(5)
        return quote_for_shell(value, shell)
    return match.group(0)


def _replacer(
    match: re.Match[str],
    args: Sequence[str],
    command: str,
    name_map: dict[str, int],
    shell: str | None,
) -> str:
    if match.group(1) is not None or match.group(4) is not None:
        return _parse_positional(match, args, command, shell)
    if match.group(2) is not None:  # {@}
        return " ".join(quote_for_shell(a, shell) for a in args)
    if match.group(3) is not None:  # {*}
        return quote_for_shell(" ".join(args), shell)
    if match.group(6) is not None:  # {name}
        name = match.group(6)
        idx = name_map[name]
        return quote_for_shell(args[idx - 1], shell) if idx <= len(args) else ""
    if match.group(7) is not None:  # {name:-default}
        name = match.group(7)
        idx = name_map[name]
        value = args[idx - 1] if idx <= len(args) else match.group(8)
        return quote_for_shell(value, shell)
    return match.group(0)


def _extract_surplus(command: str, args: Sequence[str]) -> Sequence[str]:
    """Return any args that are not consumed by positional placeholders."""
    max_ref = 0
    name_map = _named_placeholder_index_map(command)
    for m in _PLACEHOLDER_RE.finditer(command):
        if m.group(1) is not None:
            max_ref = max(max_ref, int(m.group(1)))
        elif m.group(4) is not None:
            max_ref = max(max_ref, int(m.group(4)))
        elif m.group(6) is not None:
            max_ref = max(max_ref, name_map[m.group(6)])
        elif m.group(7) is not None:
            max_ref = max(max_ref, name_map[m.group(7)])
        else:
            return []
    return args[max_ref:]


def expand(command: str, args: Sequence[str], *, shell: str | None = None) -> str:
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
    | ``{1:-val}``     | N-th arg, falling back to *val* if missing|
    +------------------+------------------------------------------+
    | ``{name}``       | Named slot, mapped to an index by order  |
    |                  | of first appearance (same as ``{N}``).   |
    +------------------+------------------------------------------+
    | ``{name:-val}`` | Named slot with default (same as         |
    |                  | ``{N:-val}``).                           |
    +------------------+------------------------------------------+

    Args:
        command: The raw alias command.
        args: Runtime positional arguments.
        shell: The shell that will execute the expanded string (e.g.
            ``"bash"``, ``"cmd"``, ``"pwsh"``). Determines the quoting
            rules applied to each interpolated argument; ``None`` falls
            back to POSIX quoting via ``shlex.quote``.

    Returns:
        The fully expanded shell command.

    Raises:
        ValueError: If a required positional placeholder is missing.
    """
    if not has_placeholders(command):
        if not args:
            return command
        quoted = " ".join(quote_for_shell(a, shell) for a in args)
        return f"{command} {quoted}"

    validate_placeholders(command, args)
    name_map = _named_placeholder_index_map(command)

    expanded = _PLACEHOLDER_RE.sub(
        lambda m: _replacer(m, args, command, name_map, shell), command
    )

    surplus = _extract_surplus(command, args)
    if surplus:
        quoted = " ".join(quote_for_shell(a, shell) for a in surplus)
        expanded = f"{expanded} {quoted}"

    return expanded
