"""Conflict detection pipeline for new alias names."""

from __future__ import annotations

import shutil

from qwik.core.models import AliasStore, validate_alias_name

__all__ = [
    "ConflictResult",
    "ConflictChecker",
    "SHELL_BUILTINS",
    "is_builtin",
]

SHELL_BUILTINS: dict[str, frozenset[str]] = {
    "bash": frozenset([
        "cd", "echo", "alias", "unalias", "set", "export", "source", "unset",
        "type", "read", "eval", "exec", "test", "true", "false", "printf",
        "shift", "exit", "return", "break", "continue", "local", "declare",
        "typeset", "readonly", "trap", "wait", "jobs", "fg", "bg", "kill",
        "ulimit", "umask", "hash", "getopts", "builtin", "command", "compgen",
        "complete", "shopt", "enable", "logout", "mapfile", "readarray",
        "help", "history", "let", "pushd", "popd", "dirs", "suspend",
        "disown", "times", "caller",
    ]),
    "zsh": frozenset([
        "setopt", "unsetopt", "autoload", "zle", "compdef", "zmodload",
        "print", "bindkey", "alias", "unalias", "set", "unset", "source",
        "echo", "printf", "test", "true", "false", "return", "break",
        "continue", "exit", "shift", "cd", "typeset", "declare", "local",
        "readonly", "trap", "wait", "jobs", "fg", "bg", "kill", "history",
        "pushd", "popd", "dirs", "suspend", "disown", "times", "hash",
        "getopts", "builtin", "command", "let",
    ]),
    "fish": frozenset([
        "abbr", "builtin", "function", "set", "test", "echo", "printf",
        "string", "contains", "switch", "begin", "end", "and", "or", "not",
        "return", "break", "continue", "source", "alias", "cd", "type",
        "command", "jobs", "fg", "bg", "kill", "bind", "complete", "pushd",
        "popd", "dirs", "history", "count", "math", "random",
    ]),
    # cmd.exe and PowerShell resolve command names case-insensitively, so
    # this set (and the lookup in is_builtin) is lowercase-normalised.
    # Built from PowerShell's real default alias table (`Get-Alias`) —
    # the short names a user would actually type and collide with — plus
    # the language's reserved keywords, rather than the long-form cmdlet
    # names an alias name can't realistically match in practice.
    "pwsh": frozenset(name.lower() for name in [
        "ac", "asnp", "cat", "cd", "chdir", "clc", "clear", "clhy", "cli",
        "clp", "cls", "clv", "cnsn", "compare", "copy", "cp", "cpi", "cpp",
        "cvpa", "dbp", "del", "diff", "dir", "dnsn", "ebp", "echo", "epal",
        "epcsv", "epsn", "erase", "etsn", "exsn", "fc", "fhx", "fl",
        "foreach", "ft", "fw", "gal", "gbp", "gc", "gcb", "gci", "gcm",
        "gcs", "gdr", "ghy", "gi", "gjb", "gl", "gm", "gmo", "gp", "gps",
        "gpv", "group", "gsn", "gsnp", "gsv", "gu", "gv", "gwmi", "h",
        "history", "icm", "iex", "ihy", "ii", "ipal", "ipcsv", "ipmo",
        "ipsn", "irm", "ise", "iwmi", "iwr", "kill", "lp", "ls", "man",
        "md", "measure", "mi", "mount", "move", "mp", "mv", "nal", "ndr",
        "ni", "nmo", "npssc", "nsn", "nv", "ogv", "oh", "popd", "ps",
        "pushd", "pwd", "r", "rbp", "rcjb", "rcsn", "rd", "rdr", "ren",
        "ri", "rjb", "rm", "rmdir", "rmo", "rni", "rnp", "rp", "rsn",
        "rsnp", "rv", "rvpa", "rwmi", "sajb", "sal", "saps", "sasv", "sbp",
        "sc", "select", "set", "shcm", "si", "sl", "sleep", "sls", "sort",
        "sp", "spjb", "spps", "spsv", "start", "sv", "swmi", "tag", "type",
        "where", "wjb", "write",
        # Language keywords (not resolvable as an alias name but included
        # for completeness of "reserved words a name shouldn't shadow").
        "if", "while", "function", "param", "return", "break", "continue",
        "switch", "try", "catch", "finally", "throw", "filter", "class",
        "enum", "using",
    ]),
    "cmd": frozenset(name.lower() for name in [
        "echo", "set", "cd", "dir", "cls", "exit", "if", "for", "rem",
        "call", "goto", "shift", "title", "prompt", "ver", "vol", "path",
        "date", "time", "type", "copy", "del", "ren", "md", "rd",
        "start", "pause", "assoc", "ftype", "pushd", "popd", "mklink",
        "move", "erase", "mkdir", "rmdir", "chdir", "setlocal", "endlocal",
        "color", "mode", "more", "tree", "where",
    ]),
    "nu": frozenset([
        "cd", "ls", "cp", "mv", "rm", "mkdir", "pwd", "echo", "cat", "open",
        "save", "table", "where", "each", "if", "let", "def", "export",
        "alias", "source", "use", "hide", "du", "ps", "sys", "date",
        "touch", "first", "last", "get", "select", "sort-by", "uniq",
        "length", "reverse", "help", "exit", "history", "which",
    ]),
    "xonsh": frozenset([
        "cd", "pwd", "exit", "history", "source", "which", "rehashx",
        "xonfig", "aliases",
        # Python keywords reachable in xonsh's Python-mode.
        "and", "or", "not", "if", "else", "elif", "for", "while", "def",
        "class", "import", "from", "as", "with", "try", "except",
        "finally", "return", "yield", "pass", "break", "continue",
        "lambda", "global", "del", "raise", "assert", "async", "await",
        "in", "is", "None", "True", "False",
    ]),
}

# Shells whose command resolution is case-insensitive. bash/zsh/fish treat
# `CD` and `cd` as genuinely different commands, so those stay exact-match;
# nu and xonsh resolve names case-sensitively too.
_CASE_INSENSITIVE_SHELLS = frozenset({"cmd", "pwsh"})


def is_builtin(name: str, shell: str | None = None) -> bool:
    """Return True if *name* is a builtin of *shell* (defaults to bash).

    Args:
        name: Candidate alias name to check.
        shell: Shell whose builtin set to consult. ``None`` means "no
            shell detected" and falls back to bash's set, same as
            before. An explicit but *unrecognised* shell name is
            deliberately **not** folded into that same fallback — it
            returns ``False`` rather than silently checking against an
            unrelated shell's builtins, since an unknown shell's real
            builtin set could contain or omit anything.
    """
    if shell is None:
        shell = "bash"
    builtins = SHELL_BUILTINS.get(shell)
    if builtins is None:
        return False
    if shell in _CASE_INSENSITIVE_SHELLS:
        return name.lower() in builtins
    return name in builtins


class ConflictResult:
    """Outcome of a conflict check.

    Attributes:
        name: The alias name that was checked.
        existing_alias: ``True`` if the name is already in the store.
        is_builtin: ``True`` if the name shadows a shell builtin.
        is_on_path: ``True`` if a binary with this name exists on ``$PATH``.
        path_location: The absolute path to the binary on ``$PATH``, if found.
        valid_syntax: ``True`` if the name passes the syntax regex.
    """

    def __init__(
        self,
        *,
        name: str,
        existing_alias: bool = False,
        is_builtin: bool = False,
        is_on_path: bool = False,
        path_location: str | None = None,
        valid_syntax: bool = True,
    ) -> None:
        """Initialise the result container.

        Args:
            name: The alias name that was checked.
            existing_alias: Whether the name already exists in the store.
            is_builtin: Whether the name is a shell builtin.
            is_on_path: Whether an executable with this name exists on PATH.
            path_location: Absolute path to the conflicting binary.
            valid_syntax: Whether the name passes the syntax regex.
        """
        self.name = name
        self.existing_alias = existing_alias
        self.is_builtin = is_builtin
        self.is_on_path = is_on_path
        self.path_location = path_location
        self.valid_syntax = valid_syntax

    @property
    def is_safe(self) -> bool:
        """Return ``True`` if no hard conflicts were found.

        A name is considered safe when it does not already exist in the
        store, is not a shell builtin, and has valid syntax.  Shadowing
        a binary on ``$PATH`` triggers a warning but is still considered
        safe.

        Returns:
            Boolean safety verdict.
        """
        return not self.existing_alias and not self.is_builtin and self.valid_syntax

    @property
    def needs_warning(self) -> bool:
        """Return ``True`` if the user should be warned before proceeding.

        Returns:
            ``True`` when the name shadows a binary on ``$PATH``.
        """
        return self.is_on_path


class ConflictChecker:
    """Four-stage conflict detection pipeline.

    The pipeline checks, in order:

    1. Existing registered alias.
    2. Shell builtin.
    3. Binary on ``$PATH``.
    4. Valid syntax (regex ``^[A-Za-z_][A-Za-z0-9_-]*$``).
    """

    def __init__(self, store: AliasStore) -> None:
        """Initialise the checker with a reference store.

        Args:
            store: The current alias database used for the "already
                registered" check.
        """
        self._store = store

    def check(self, name: str, shell: str | None = None) -> ConflictResult:
        """Run the full conflict pipeline against *name*.

        Args:
            name: Candidate alias name.
            shell: Shell name whose builtin set should be consulted.
                Defaults to ``bash`` when ``None``.

        Returns:
            A :class:`ConflictResult` summarising all findings.
        """
        existing = name in self._store.aliases
        builtin = is_builtin(name, shell)
        path_bin = shutil.which(name)
        is_on_path = path_bin is not None

        try:
            validate_alias_name(name)
            valid = True
        except ValueError:
            valid = False

        return ConflictResult(
            name=name,
            existing_alias=existing,
            is_builtin=builtin,
            is_on_path=is_on_path,
            path_location=path_bin,
            valid_syntax=valid,
        )
