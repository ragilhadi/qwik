"""Conflict detection pipeline for new alias names."""

from __future__ import annotations

import shutil

from qwik.core.models import AliasStore, validate_alias_name

__all__ = [
    "ConflictResult",
    "ConflictChecker",
    "SHELL_BUILTINS",
]

# Common shell builtins that should not be shadowed lightly.
SHELL_BUILTINS: frozenset[str] = frozenset(
    [
        "cd",
        "echo",
        "alias",
        "unalias",
        "set",
        "export",
        "source",
        "unset",
        "type",
        "read",
        "eval",
        "exec",
        "test",
        "true",
        "false",
        "printf",
        "shift",
        "exit",
        "return",
        "break",
        "continue",
        "local",
        "declare",
        "typeset",
        "readonly",
        "trap",
        "wait",
        "jobs",
        "fg",
        "bg",
        "kill",
        "ulimit",
        "umask",
        "hash",
        "getopts",
        "builtin",
        "command",
        "compgen",
        "complete",
        "shopt",
        "enable",
        "logout",
        "mapfile",
        "readarray",
        "help",
        "history",
        "let",
        "pushd",
        "popd",
        "dirs",
        "suspend",
        "disown",
        "times",
        "caller",
    ]
)


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

    def check(self, name: str) -> ConflictResult:
        """Run the full conflict pipeline against *name*.

        Args:
            name: Candidate alias name.

        Returns:
            A :class:`ConflictResult` summarising all findings.
        """
        existing = name in self._store.aliases
        builtin = name in SHELL_BUILTINS
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
