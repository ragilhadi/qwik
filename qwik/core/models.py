"""Pydantic models for alias data."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "Alias",
    "AliasStore",
    "validate_alias_name",
]

# Regex used in conflict checks and model validation.
_ALIAS_NAME_RE: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def validate_alias_name(name: str) -> str:
    """Ensure *name* is a legal alias identifier.

    Legal names start with a letter or underscore and contain only
    letters, digits, underscores, and hyphens.

    Args:
        name: The candidate alias name.

    Returns:
        The cleaned *name* if it is valid.

    Raises:
        ValueError: If *name* contains whitespace, shell metacharacters,
            or otherwise fails the syntax check.
    """
    if not _ALIAS_NAME_RE.match(name):
        raise ValueError(
            f'Invalid name "{name}": names must match ' r"^[A-Za-z_][A-Za-z0-9_-]*$"
        )
    return name


class Alias(BaseModel):
    """A single alias definition.

    Attributes:
        command: The shell command the alias expands to.  May contain
            template placeholders such as ``{1}``, ``{@}``, ``{*}``,
            or ``{1:-default}``.
        tag: Optional list of categorical tags (e.g. ``git``, ``work``).
        description: Human-readable explanation of the alias.
        enabled: Whether the alias is currently active.  Disabled aliases
            are kept in the store but ignored by the shell hook.
        created_at: ISO-8601 UTC timestamp of creation.
        updated_at: ISO-8601 UTC timestamp of last modification.
        last_used: ISO-8601 UTC timestamp of the most recent execution,
            or ``None`` if never run.
        run_count: Total number of times the alias has been executed.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    command: str
    tag: list[str] = Field(default_factory=list)
    description: str = ""
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_used: datetime | None = None
    run_count: int = 0

    @field_validator("tag", mode="before")
    @classmethod
    def _coerce_tag(cls, v: Any) -> list[str]:
        """Coerce a comma-separated string into a list of tags."""
        if isinstance(v, str):
            return [t.strip() for t in v.split(",") if t.strip()]
        if v is None:
            return []
        return list(v)

    @model_validator(mode="after")
    def _check_updated(self) -> "Alias":
        """Ensure ``updated_at`` is not earlier than ``created_at``."""
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        return self

    def bump_usage(self) -> None:
        """Update ``last_used`` and increment ``run_count``."""
        self.last_used = datetime.now(timezone.utc)
        self.run_count += 1

    def format_last_used(self) -> str:
        """Return a human-readable relative time for ``last_used``.

        Returns:
            A friendly string such as ``"2 min ago"`` or ``"never"``.
        """
        if self.last_used is None:
            return "never"
        delta = datetime.now(timezone.utc) - self.last_used
        if delta.days > 0:
            return f"{delta.days} day{'s' if delta.days > 1 else ''} ago"
        hours = delta.seconds // 3600
        if hours > 0:
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        minutes = delta.seconds // 60
        if minutes > 0:
            return f"{minutes} min ago"
        return "just now"


class AliasStore(BaseModel):
    """Top-level container for the entire alias database.

    Attributes:
        aliases: Mapping from alias name to :class:`Alias`.
        version: Schema version for forward-compatibility.
    """

    model_config = ConfigDict(extra="forbid")

    aliases: dict[str, Alias] = Field(default_factory=dict)
    version: int = 1

    @model_validator(mode="after")
    def _validate_names(self) -> "AliasStore":
        """Run every alias key through the name validator."""
        for name in self.aliases:
            validate_alias_name(name)
        return self

    def get(self, name: str) -> Alias | None:
        """Look up an alias by name.

        Args:
            name: Alias identifier.

        Returns:
            The :class:`Alias` if it exists, otherwise ``None``.
        """
        return self.aliases.get(name)

    def add(self, name: str, alias: Alias, *, force: bool = False) -> None:
        """Insert a new alias into the store.

        Args:
            name: Alias identifier.
            alias: The alias definition to store.
            force: If ``True``, overwrite an existing alias.  Otherwise a
                :class:`KeyError` is raised.

        Raises:
            KeyError: If *name* already exists and *force* is ``False``.
        """
        validate_alias_name(name)
        if name in self.aliases and not force:
            raise KeyError(f'Alias "{name}" already exists.')
        self.aliases[name] = alias

    def remove(self, name: str) -> Alias:
        """Delete an alias from the store.

        Args:
            name: Alias identifier.

        Returns:
            The removed :class:`Alias`.

        Raises:
            KeyError: If *name* does not exist.
        """
        if name not in self.aliases:
            raise KeyError(f'Alias "{name}" does not exist.')
        return self.aliases.pop(name)

    def rename(self, old: str, new: str) -> None:
        """Rename an alias while preserving metadata.

        Args:
            old: Current alias name.
            new: Desired alias name.

        Raises:
            KeyError: If *old* does not exist.
            KeyError: If *new* already exists.
        """
        validate_alias_name(new)
        if old not in self.aliases:
            raise KeyError(f'Alias "{old}" does not exist.')
        if new in self.aliases:
            raise KeyError(f'Alias "{new}" already exists.')
        self.aliases[new] = self.aliases.pop(old)
        self.aliases[new].updated_at = datetime.now(timezone.utc)
