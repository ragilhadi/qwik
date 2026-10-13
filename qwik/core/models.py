"""Pydantic models for alias data."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from qwik.core.platform import PLATFORMS, variant_key
from qwik.core.shell_detect import KNOWN_SHELLS

__all__ = [
    "Alias",
    "AliasStore",
    "validate_alias_name",
    "validate_variant_key",
]

# Regex used in conflict checks and model validation.
_ALIAS_NAME_RE: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")

# Regex validating group names (same syntax rules as alias names).
_GROUP_NAME_RE: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")

# Regex matching a platform-conditional command variant key: either the
# platform-level fallback (``command_macos``) or a shell-specific refinement
# (``command_windows_pwsh``).  Storage stays flat TOML keys so hand-editing
# remains easy; the :meth:`Alias._collect_variants` validator pops these
# into the single ``command_variants`` dict field.
_VARIANT_KEY_RE: re.Pattern[str] = re.compile(
    r"^command_(?P<platform>"
    + "|".join(PLATFORMS)
    + r")(?:_(?P<shell>"
    + "|".join(sorted(KNOWN_SHELLS))
    + r"))?$"
)


def _invalid_variant_key(key: str) -> ValueError:
    """Build the actionable error for a bad ``command_*`` variant key."""
    return ValueError(
        f'Invalid variant key "{key}": platform variants must be one of '
        f"command_{', command_'.join(PLATFORMS)}; per-shell variants add the "
        f"underscored shell name (one of {', '.join(sorted(KNOWN_SHELLS))}), "
        'e.g. "command_windows_pwsh".'
    )


def validate_variant_key(key: str) -> str:
    """Ensure *key* is a legal platform-variant key.

    Args:
        key: A ``command_<platform>`` or ``command_<platform>_<shell>``
            key candidate.

    Returns:
        *key* unchanged if it is valid.

    Raises:
        ValueError: If *key* does not follow the variant-key grammar.
    """
    if _VARIANT_KEY_RE.match(key) is None:
        raise _invalid_variant_key(key)
    return key


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
        raise ValueError(f'Invalid name "{name}": names must match ' r"^[A-Za-z_][A-Za-z0-9_-]*$")
    return name


class Alias(BaseModel):
    """A single alias definition.

    Attributes:
        command: The shell command the alias expands to.  May contain
            template placeholders such as ``{1}``, ``{@}``, ``{*}``,
            or ``{1:-default}``.  Serves as the fallback when no
            platform-specific variant applies.
        command_variants: Optional per-platform (and per-shell) command
            variants, keyed by ``command_<platform>`` or
            ``command_<platform>_<shell>`` (e.g. ``{"command_macos": "open {1}"}``).
            On disk these stay as flat TOML keys next to ``command``; the
            ``_collect_variants`` validator collects them here.  Resolved
            via :meth:`resolve_command`; the base ``command`` is required
            and used as the last-resort fallback.
        tag: Optional list of categorical tags (e.g. ``git``, ``work``).
        group: Optional canonical primary group for the alias.  At most one
            group may be assigned to an alias; tags are free-form labels and
            many may be assigned.
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
    command_variants: dict[str, str] = Field(default_factory=dict)
    tag: list[str] = Field(default_factory=list)
    group: str | None = None
    description: str = ""
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_used: datetime | None = None
    run_count: int = 0

    @model_validator(mode="before")
    @classmethod
    def _collect_variants(cls, v: Any) -> Any:
        """Collect flat ``command_<platform>[_<shell>]`` keys before validation.

        The store (and hand-edited TOML) keeps variants as flat keys next to
        ``command``::

            command = "xdg-open {1}"
            command_macos = "open {1}"
            command_windows_pwsh = "start {1}"

        This validator pops every key matching that grammar into the single
        ``command_variants`` dict field — running *before* the extra check,
        so ``extra="forbid"`` stays intact.  A ``command_variants`` mapping
        supplied directly (JSON exports, programmatic dumps) is merged into
        the same dict, so both shapes validate.  Any other ``command_*`` key
        is rejected with an actionable message rather than a bare
        "extra inputs not permitted" from the forbid check.

        Empty or whitespace-only values are dropped, treating a blanked
        line in a hand-edited store as "no variant".
        """
        if not isinstance(v, dict):
            return v
        data = dict(v)
        variants: dict[str, str] = dict(data.pop("command_variants", None) or {})
        for key in [k for k in data if isinstance(k, str) and k.startswith("command_")]:
            if _VARIANT_KEY_RE.match(key) is None:
                raise _invalid_variant_key(key)
            variants[key] = data.pop(key)
        for key in variants:
            if _VARIANT_KEY_RE.match(key) is None:
                raise _invalid_variant_key(key)
        data["command_variants"] = {
            key: str(val) for key, val in sorted(variants.items()) if str(val).strip()
        }
        return data

    @field_validator("tag", mode="before")
    @classmethod
    def _coerce_tag(cls, v: Any) -> list[str]:
        """Coerce a comma-separated string into a list of tags."""
        if isinstance(v, str):
            return [t.strip() for t in v.split(",") if t.strip()]
        if v is None:
            return []
        return list(v)

    @field_validator("group", mode="before")
    @classmethod
    def _coerce_group(cls, v: Any) -> str | None:
        """Normalise the optional group field.

        Accept ``None`` or a string.  Whitespace is stripped; empty or
        whitespace-only values become ``None``.  Non-empty values must
        satisfy the group-name regex.
        """
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError(f'Invalid group "{v!r}": must be a string or None.')
        cleaned = v.strip()
        if not cleaned:
            return None
        if not _GROUP_NAME_RE.match(cleaned):
            raise ValueError(
                f'Invalid group "{cleaned}": groups must match ' r"^[A-Za-z_][A-Za-z0-9_-]*$"
            )
        return cleaned

    @model_validator(mode="after")
    def _check_updated(self) -> Alias:
        """Ensure ``updated_at`` is not earlier than ``created_at``."""
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        return self

    def resolve_command(self, platform: str | None = None, shell: str | None = None) -> str:
        """Resolve the effective command for *platform* and *shell*.

        First match wins, in order:

        1. ``command_<platform>_<shell>`` — the most specific variant
           (e.g. ``command_windows_pwsh``), only when both arguments are
           given;
        2. ``command_<platform>`` — the platform fallback
           (e.g. ``command_macos``);
        3. ``command`` — the base fallback, always present.

        Args:
            platform: One of the platform keys
                (:data:`qwik.core.platform.PLATFORMS`), or ``None`` to skip
                platform variants entirely.
            shell: A registered shell name (e.g. ``"pwsh"``), or ``None``
                for shell-agnostic resolution.

        Returns:
            The resolved command string.
        """
        if platform and shell:
            variant = self.command_variants.get(variant_key(platform, shell))
            if variant:
                return variant
        if platform:
            variant = self.command_variants.get(variant_key(platform))
            if variant:
                return variant
        return self.command

    def bump_usage(self) -> None:
        """Update ``last_used`` and increment ``run_count``."""
        self.last_used = datetime.now(UTC)
        self.run_count += 1

    def format_last_used(self) -> str:
        """Return a human-readable relative time for ``last_used``.

        Returns:
            A friendly string such as ``"2 min ago"`` or ``"never"``.
        """
        if self.last_used is None:
            return "never"
        delta = datetime.now(UTC) - self.last_used
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
        version: Schema version for forward-compatibility.  v2 introduces
            platform-conditional ``command_<platform>[_<shell>]`` variants;
            older qwik versions refuse a v2 file via the migration version
            gate with an actionable upgrade message.
    """

    model_config = ConfigDict(extra="forbid")

    aliases: dict[str, Alias] = Field(default_factory=dict)
    overlay_aliases: dict[str, Alias] = Field(default_factory=dict)
    version: int = 2

    @model_validator(mode="after")
    def _validate_names(self) -> AliasStore:
        """Run every alias key through the name validator."""
        for name in self.aliases:
            validate_alias_name(name)
        for name in self.overlay_aliases:
            validate_alias_name(name)
        return self

    def all_aliases(self) -> dict[str, Alias]:
        """Return merged view: user aliases take precedence over overlay."""
        merged = dict(self.overlay_aliases)
        merged.update(self.aliases)
        return merged

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
        self.aliases[new].updated_at = datetime.now(UTC)
