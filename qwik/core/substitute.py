"""Argument substitution engine for alias templates."""

from __future__ import annotations

import os
import re
import shlex
from collections.abc import Sequence

__all__ = [
    "expand",
    "find_unrecognized_braces",
    "has_placeholders",
    "placeholder_arity",
    "placeholders_compatible",
    "quote_for_shell",
    "render_native",
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


def placeholder_arity(command: str) -> int | None:
    """Return the maximum positional index *command* can consume.

    Used to reject platform-conditional variants whose argument shape
    disagrees with the base command (``xdg-open {1}`` vs ``open {1} {2}``).

    Args:
        command: The alias command string to inspect.

    Returns:
        The 1-based maximum referenced positional index — counting
        ``{N}``, ``{N:-default}``, and named placeholders (mapped to their
        positional slots) — or ``0`` when *command* has no placeholders
        (append mode consumes every argument), or ``None`` when the
        command contains ``{@}``/``{*}`` and is therefore variadic,
        which is compatible with any arity.
    """
    if _PLACEHOLDER_RE.search(command) is None:
        return 0
    arity = 0
    name_map = _named_placeholder_index_map(command)
    for match in _PLACEHOLDER_RE.finditer(command):
        if match.group(2) is not None or match.group(3) is not None:
            return None
        if match.group(1) is not None:
            arity = max(arity, int(match.group(1)))
        elif match.group(4) is not None:
            arity = max(arity, int(match.group(4)))
        elif match.group(6) is not None:
            arity = max(arity, name_map[match.group(6)])
        elif match.group(7) is not None:
            arity = max(arity, name_map[match.group(7)])
    return arity


def placeholders_compatible(base: str, variant: str) -> bool:
    """Return ``True`` when *variant* can safely replace *base* on a platform.

    Both commands must agree on their placeholder arity
    (:func:`placeholder_arity`), except that variadic commands (``{@}`` /
    ``{*}``) are compatible with any shape.

    Args:
        base: The base alias command.
        variant: The platform/shell variant command.

    Returns:
        Boolean indicating whether the two commands consume arguments
        in a compatible way.
    """
    base_arity = placeholder_arity(base)
    variant_arity = placeholder_arity(variant)
    if base_arity is None or variant_arity is None:
        return True
    return base_arity == variant_arity


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
    valid_spans = [(m.start(), m.end()) for m in _PLACEHOLDER_RE.finditer(command)]

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
            or (inner[:1].isascii() and (inner[:1].isalnum() or inner.startswith("_")))
        ):
            offenders.append(m.group(0))
    return offenders


def _raise_invalid_index(idx: int, command: str) -> None:
    """Raise ValueError for a 0/negative positional placeholder."""
    raise ValueError(
        f'Invalid placeholder {{{idx}}} in alias: "{command}". '
        f"Positional placeholders must be 1-based ({{1}}, {{2}}, ...)."
    )


def _validate_placeholder_index(idx: int, command: str) -> None:
    """Raise ValueError for a 0/negative positional placeholder index."""
    if idx < 1:
        _raise_invalid_index(idx, command)


def _validate_positional_arg(idx: int, args: Sequence[str], command: str) -> None:
    """Raise ValueError when ``{idx}`` is invalid or beyond the supplied args."""
    _validate_placeholder_index(idx, command)
    if idx > len(args):
        raise ValueError(
            f'Missing argument {idx} for alias: "{command}" (received {len(args)} argument(s))'
        )


def _validate_named_arg(
    name: str, name_map: dict[str, int], args: Sequence[str], command: str
) -> None:
    """Raise ValueError when a named placeholder lacks its positional arg."""
    idx = name_map[name]
    if idx > len(args):
        raise ValueError(
            f"Missing argument for placeholder {{{name}}} "
            f'(position {idx}) in alias: "{command}" '
            f"(received {len(args)} argument(s))"
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
            _validate_positional_arg(int(match.group(1)), args, command)
        elif match.group(4) is not None:
            _validate_placeholder_index(int(match.group(4)), command)
        elif match.group(6) is not None:
            _validate_named_arg(match.group(6), name_map, args, command)


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

    expanded = _PLACEHOLDER_RE.sub(lambda m: _replacer(m, args, command, name_map, shell), command)

    surplus = _extract_surplus(command, args)
    if surplus:
        quoted = " ".join(quote_for_shell(a, shell) for a in surplus)
        expanded = f"{expanded} {quoted}"

    return expanded


# ---------------------------------------------------------------------------
# Native template rendering (compile-time, not runtime)
# ---------------------------------------------------------------------------

# Shells for which this module can translate the placeholder grammar into
# native (evaluator-local) argument syntax.  Deliberately conservative:
#
# - cmd.exe: doskey macros cannot interpolate positional arguments at all.
# - xonsh: native splicing requires emitting the command text into xonsh's
#   own ``![...]`` subprocess mode, whose string parsing (``\``-escapes,
#   Python-like literals) diverges from POSIX in exactly the adversarial
#   quoting cases the quoting tests pin; a wrong translation silently
#   changes the alias, so xonsh keeps the ``qwik run`` wrapper.
# - nu: native arguments require typed ``def`` signatures and nu's pipeline
#   semantics (no shell string) differ from ``qwik run``'s; also keeps the
#   wrapper.
_NATIVE_SHELLS = frozenset({"bash", "zsh", "fish", "pwsh"})

# A placeholder appearing inside shell single quotes can never be
# interpolated by the shell's argument machinery (bash/zsh/fish/xonsh all
# treat '...' as literal).  pwsh also interpolates no variables inside its
# single-quoted strings.  When any single-quoted span contains a placeholder,
# native rendering would change the alias's meaning, so the caller must keep
# the `qwik run` wrapper for that alias.  Quote characters *inside* a
# placeholder's default value ({name:-don't}) belong to the value, not to
# the shell, so placeholder spans are masked out before the quote scan runs.
_SINGLE_QUOTE_SPAN: re.Pattern[str] = re.compile(r"'[^']*'")
_MASK = "\x00"


def _has_placeholder_in_single_quotes(command: str) -> bool:
    """Detect a placeholder inside single-quoted shell text."""
    masked = _PLACEHOLDER_RE.sub(lambda m: _MASK * len(m.group(0)), command)
    return any(_MASK in span.group(0) for span in _SINGLE_QUOTE_SPAN.finditer(masked))


# fish's `echo` argument in the {N:-default} translation must be a literal
# even when the default carries quotes/backslashes: fish's backslash escape
# rules differ from POSIX (\\ is an escape outside quotes there too), so fish
# quoting is applied with its own doubling rule, never shlex's.
def _fish_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def native_template_capable(shell: str | None) -> bool:
    """Return ``True`` if *shell* can express the placeholder grammar natively.

    Only a conservative set of shells is claimed.  ``cmd`` (doskey) has no
    positional interpolation at all and ``nu`` evaluates arguments through a
    typed pipeline rather than a word list; both keep the ``qwik run``
    wrapper, which they already use for template mode.

    Setting ``QWIK_NO_NATIVE=1`` in the environment (or passing
    ``--no-native`` to ``qwik init``, which sets it for the render) forces
    every shell back onto the ``qwik run`` wrapper — the escape hatch if a
    native rendering turns out to be wrong in the field.
    """
    if os.environ.get("QWIK_NO_NATIVE"):
        return False
    return shell in _NATIVE_SHELLS


def native_safe(command: str) -> bool:
    """Return ``False`` when native rendering would change *command*'s meaning.

    Two constructs must be rejected:

    1. A placeholder inside single-quoted shell text.  ``qwik run``
       interpolates placeholders everywhere in the command string, but
       bash/zsh/fish/pwsh never expand argument references inside
       ``'...'`` — compiling ``'branch is {1}'`` would silently change the
       alias.  The check is a conservative over-approximation: *any*
       single-quoted span in the command forces the wrapper.

    2. A placeholder inside a *composite* double-quoted word — quoted text
       with the placeholder glued to neighbouring characters
       (``"p={1}"``, ``"a {1} b"``).  ``expand()`` quotes the substituted
       value with POSIX rules at run-time, native substitution splices the
       raw value; the whole-word case (``"{1}"``) is byte-identical for
       single args, the embedded cases split differently when the value
       contains spaces.  Whole-word placeholders compile natively (the
       emitted ref is unquoted there and inherits the command's own
       quotes); embedded ones keep the wrapper.
    """
    if _has_placeholder_in_single_quotes(command):
        return False
    for match in _PLACEHOLDER_RE.finditer(command):
        before = command[: match.start()]
        after = command[match.end() :]
        # Inside a double-quoted word?  Track quote parity left of the
        # placeholder, considering only unescaped double quotes.
        left_quotes = before.replace('\\"', "").count('"')
        if left_quotes % 2 == 0:
            continue  # unquoted context: the mapping adds its own quotes
        # Quoted context: the placeholder must BE the whole word — the
        # characters left/right of it must be the word's opening/closing
        # quote (or end-of-command).
        if not (before.endswith('"') and after.startswith(('"', "", " ", "\t"))):
            return False
    return True


def render_native(command: str, shell: str) -> str | None:
    """Compile placeholder syntax into native *shell* argument references.

    This is the compile-time counterpart of :func:`expand`: instead of
    emitting a ``qwik run`` wrapper that pays a Python process spawn on
    every invocation, the emitted function body references the shell's own
    positional argument machinery, costing microseconds.

    Mappings are chosen so that, for every argument tuple, the natively
    rendered alias and ``qwik run`` produce the same output (the
    differential test pins this over a corpus including spaced, quoted and
    metacharacter-bearing arguments).  The sharp edges that shaped each
    translation:

    - bash/zsh ``"${N-}"`` substitutes the empty string for a missing
      positional — exactly what ``expand()`` does; ``"${@:N}"`` / the fish
      slice ``$argv[N..-1]`` forward surplus args, matching ``expand()``'s
      surplus append.
    - A placeholder inside a *composite* double-quoted word
      (``"a {1} b"``, ``"p={1}"``) keeps the wrapper: ``expand()`` quotes
      the substituted value at run-time, while native substitution splices
      the raw value — byte-identical for the whole-word case
      (``"{1}"`` → ``"${1-}"``), divergent for embedded ones (an argument
      containing spaces would split differently).  Whole-word quoting is
      the overwhelmingly common shape (``git checkout "{1}"`` etc.).
    - fish splits command- and variable-substitution output on newlines;
      a default carrying spaces must be protected by ``string collect``.
    - pwsh has no scalar join expression for ``{*}``; such an alias keeps
      the wrapper.

    ============  ==================  ====================  =========================
    Placeholder   bash / zsh          fish                  pwsh
    ============  ==================  ====================  =========================
    ``{N}``       ``"${N-}"``         ``$argv[N]``          ``$args[N-1]``
    ``{@}``       ``"$@"``            ``$argv``             ``@args``
    ``{*}``       ``"$*"``            ``$argv``             (keeps the wrapper)
    ``{N:-x}``    ``"${N:-x}"``       ``if count … collect`` ``$(if …)`
    ``{name}``    index-mapped, then as ``{N}``
    ============  ==================  ====================  =========================

    A missing positional renders as a *dropped word* on the list-semantics
    shells (fish/pwsh evaluate ``$argv[N]``/``$args[N-1]`` to nothing) and
    as the empty string on bash/zsh — both diverge from ``expand()``
    there or agree as shown in the differential corpus, which excludes the
    diverging tuples (see the corpus generator's comment).

    Returns:
        The natively rendered command, or ``None`` when the combination
        cannot be expressed natively and the caller must keep the
        ``qwik run`` wrapper.  ``None`` is returned for shells outside
        :data:`_NATIVE_SHELLS` and for commands whose meaning native
        rendering would change (see :func:`native_safe`).

    Raises:
        ValueError: If *command* contains structurally invalid placeholders
            (propagated so ``qwik add``/``edit`` surface the same errors as
            the runtime engine).
    """
    if not native_template_capable(shell) or not native_safe(command):
        return None

    # Static validation first, so `render_native` never emits a broken
    # function body for a command the runtime engine would reject.
    validate_placeholders_static(command)
    name_map = _named_placeholder_index_map(command)

    def syntax(placeholder: str) -> str | None:
        """Return native syntax for one placeholder, or ``None``."""
        match = _PLACEHOLDER_RE.fullmatch(placeholder)
        assert match is not None
        if match.group(2) is not None:  # {@}
            return {
                "bash": '"$@"',
                "zsh": '"$@"',
                "fish": "(string collect -- $argv)",
                "pwsh": "@args",
            }[shell]
        if match.group(3) is not None:  # {*}
            return {
                "bash": '"$*"',
                "zsh": '"$*"',
                "fish": None,  # single re-quoted string needs eval; keeps wrapper
                "pwsh": None,  # no scalar join; keeps the wrapper
            }[shell]
        idx: int | None = None
        default: str | None = None
        if match.group(1) is not None:
            idx = int(match.group(1))
        elif match.group(4) is not None:
            idx = int(match.group(4))
            default = match.group(5)
        elif match.group(6) is not None:
            idx = name_map[match.group(6)]
        elif match.group(7) is not None:
            idx = name_map[match.group(7)]
            default = match.group(8)
        if idx is None or idx < 1:
            return None  # {0} is invalid everywhere; validation rejects it too
        if shell in ("bash", "zsh"):
            if default is not None:
                return f'"${{{idx}:-{default}}}"'
            return f'"${{{idx}-}}"'
        if shell == "fish":
            if default is not None:
                # fish splits command-substitution output on newlines and
                # variable expansion on elements; `string collect --`
                # preserves the single value.  The default is emitted as a
                # double-quoted fish literal (single quotes inside it need
                # no escaping there — verified: dq"quote and f'q survive).
                return (
                    "(if count $argv > "
                    + str(idx - 1)
                    + "; string collect -- $argv["
                    + str(idx)
                    + ']; else; string collect -- "'
                    + default
                    + '"; end)'
                )
            return f"(string collect -- $argv[{idx}])"
        if shell == "pwsh":
            if default is not None:
                return (
                    "$(if ($args.Count >= "
                    + str(idx)
                    + ") { $args["
                    + str(idx - 1)
                    + "] } else { '"
                    + default.replace("'", "''")
                    + "' })"
                )
            return f"$args[{idx - 1}]"
        return None

    # Fail closed: if any placeholder lacks a native translation, keep the
    # wrapper rather than emitting a half-converted body.
    for m in _PLACEHOLDER_RE.finditer(command):
        if syntax(m.group(0)) is None:
            return None

    def replace(match: re.Match[str]) -> str:
        translated = syntax(match.group(0))
        assert translated is not None
        return translated

    expanded = _PLACEHOLDER_RE.sub(replace, command)

    # Quote-context fixup for bash/zsh: the mappings emit *quoted* refs
    # ('"${1-}"'); when the command already quotes the placeholder
    # ('"{1}"'), the emitted quotes would double up.  Collapse the doubled
    # sequence — the command's own quotes then quote the ref, which is
    # exactly the whole-word case native_safe admitted.
    if shell in ("bash", "zsh"):
        expanded = expanded.replace('"""', '"').replace('""$${', "${").replace('"""', '"')
        expanded = expanded.replace('""', '"')

    # expand() appends args not consumed by any positional placeholder
    # (quoted, space-joined) after the template; the native body must do
    # the same or surplus args would silently vanish.  {@} and {*} make
    # the tail redundant (they already carry every arg).
    max_ref = 0
    uses_every = False
    for m in _PLACEHOLDER_RE.finditer(command):
        if m.group(2) is not None or m.group(3) is not None:
            uses_every = True
        else:
            s = syntax(m.group(0))
            if s is None:
                return None
            idx = _placeholder_index(m, name_map)
            if idx is not None:
                max_ref = max(max_ref, idx)
    if uses_every:
        return expanded
    if shell == "pwsh":
        # pwsh cannot splat "args beyond index N" without a helper variable
        # (@args[N..] yields a descending slice for Count < N, silently
        # reordering args).  Without {@}/{*} carrying every arg, surplus
        # args could vanish — fail closed and keep the wrapper.
        return None
    tail = _surplus_tail(shell, max_ref)
    expanded = expanded.rstrip()
    return f"{expanded} {tail}" if tail else expanded


def _placeholder_index(match: re.Match[str], name_map: dict[str, int]) -> int | None:
    """Return the positional index one placeholder match refers to."""
    if match.group(1) is not None or match.group(4) is not None:
        return int(match.group(1) or match.group(4))
    if match.group(6) is not None:
        return name_map[match.group(6)]
    if match.group(7) is not None:
        return name_map[match.group(7)]
    return None


def _surplus_tail(shell: str, after: int) -> str:
    """Return the shell syntax appending args beyond index *after*.

    Mirrors :func:`expand`'s surplus append: every non-consumed argument,
    forwarded as the shell would forward it.  bash/zsh use the range form
    ``"${@:N}"``, which expands to zero words when absent (verified on
    bash 5.3 / zsh 5.9); fish uses the slice ``$argv[N..-1]`` guarded by
    ``string collect`` so multi-word arguments stay whole.  pwsh cannot
    express "args from N+1 on" as a splat of a slice without a helper
    variable, so its callers keep the wrapper when surplus args are
    possible.
    """
    start = after + 1
    if shell in ("bash", "zsh"):
        return f'"${{@:{start}}}"'
    if shell == "fish":
        return f"(string collect -- $argv[{start}..-1])"
    return ""
