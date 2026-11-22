"""Abstract base class and per-shell renderers for shell hook generation."""

from __future__ import annotations

import functools
import importlib.metadata
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, cast

from qwik.core.platform import current_platform

if TYPE_CHECKING:
    from pathlib import Path

    from qwik.core.models import Alias

__all__ = [
    "SUPPORTED_SHELLS",  # noqa: F822 — provided lazily by module __getattr__ below
    "ShellRenderer",
    "get_renderer",
    "supported_shells",
]

_ENTRY_POINT_GROUP = "qwik.shell_renderers"


@functools.cache
def supported_shells() -> tuple[str, ...]:
    """Return all registered shell identifiers, sorted.

    Discovers shells via the ``qwik.shell_renderers`` entry-point group.
    Entry-point discovery walks installed-distribution metadata on disk,
    so the result is cached: at most one scan per process, and only when
    something actually needs it (not at import time — most invocations,
    like ``qwik add``, never call this at all).
    """
    eps = importlib.metadata.entry_points(group=_ENTRY_POINT_GROUP)
    return tuple(sorted(ep.name for ep in eps))


@functools.cache
def _renderer_registry() -> dict[str, type]:
    """Return ``{shell_name: renderer_class}``, loaded and cached once."""
    return {ep.name: ep.load() for ep in importlib.metadata.entry_points(group=_ENTRY_POINT_GROUP)}


def __getattr__(name: str) -> Any:
    """Compute ``SUPPORTED_SHELLS`` lazily on first access (PEP 562).

    Kept as a module attribute for backward compatibility with any
    ``from qwik.shells.base import SUPPORTED_SHELLS`` import, but no
    longer computed eagerly at import time.
    """
    if name == "SUPPORTED_SHELLS":
        return supported_shells()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class ShellRenderer(ABC):
    """ABC for emitting shell-native alias definitions.

    Each concrete subclass must produce syntax that, when evaluated by
    the target shell, makes every *enabled* alias callable as a real
    command (either via ``alias`` or via a wrapper function).
    """

    @property
    @abstractmethod
    def shell_name(self) -> str:
        """Return the canonical shell identifier."""
        ...

    @abstractmethod
    def render_alias(self, name: str, alias: Alias) -> str:
        """Return a single alias/function definition for *name*.

        Args:
            name: Alias identifier.
            alias: The alias definition.

        Returns:
            A string containing shell-native code (e.g. ``alias gs='git status'``).
        """
        ...

    #: Native template-mode capability.
    #:
    #: Subclasses whose shell can interpolate positional arguments directly
    #: (bash, zsh, fish, pwsh, xonsh) opt in by overriding this to ``True``
    #: and calling :meth:`render_template_alias_body` (or the
    #: :func:`qwik.core.substitute.render_native` engine) from
    #: ``render_alias``.  The base implementation is ``False``: template-mode
    #: aliases keep the ``qwik run`` wrapper, which every renderer already
    #: emits — so third-party plugin renderers don't change behaviour until
    #: their author chooses to support native templates.
    supports_native_templates: bool = False

    # Comment emitted in the generated hook whenever a template-mode alias
    # is rendered through the `qwik run` wrapper by a renderer that does not
    # support native templates (structural opt-out: cmd, nu, plugins).  Keeps
    # the emitted hook self-explaining and greppable.
    _native_skip_comment = (
        "# {name}: template mode via `qwik run` ({shell} does not render"
        " argument templates natively)"
    )

    def render_template_native_comment(self, name: str) -> str:
        """Return the opt-out comment line for template alias *name*."""
        return self._native_skip_comment.format(name=name, shell=self.shell_name)

    #: Shell supports programmable argument completion.
    #:
    #: Subclasses whose shell can register a completion function
    #: (bash, zsh, fish, pwsh) opt in by overriding this to ``True`` and
    #: implementing :meth:`render_completion_alias`.  The default ``False``
    #: means renderers emit nothing for completions — third-party plugin
    #: renderers keep their behaviour until the author opts in.
    supports_completions: bool = False

    def render_completion_alias(self, name: str, alias: Alias) -> str:
        """Return a completion definition for *name*, or ``""``.

        Args:
            name: Alias identifier.
            alias: The alias definition (may carry a ``complete`` mapping).

        Returns:
            A string containing the shell-native completion definition, or
            ``""`` when the alias declares no completion.
        """
        return ""

    def render_header(self) -> str:
        """Return an optional header emitted before alias definitions."""
        return ""

    def render_footer(self) -> str:
        """Return an optional footer emitted after alias definitions."""
        return ""

    # Directory-change hook lines for project layer refresh.  Renderers
    # whose shell can re-evaluate on chdir (bash, zsh, fish) override
    # ``render_footer`` to append these when a project layer exists.
    _cd_refresh_footer = """\
# qwik project layer: re-resolve .qwik.toml on directory change
{refresh_fn} {{
    eval "$(qwik init {shell} 2>/dev/null)"
}}
{hook_line}"""

    def render_cd_refresh_footer(self) -> str:
        """Return the footer re-rendering the hook on directory change."""
        return ""

    def rc_path(self) -> Path | None:
        """Return the RC file path for this shell, or ``None`` if unsupported."""
        return None

    def install_hook_line(self) -> str | None:
        """Return the hook line to append to the RC file, or ``None``."""
        return None

    def render_all(
        self,
        aliases: dict[str, Alias],
        *,
        platform: str | None = None,
        shell: str | None = None,
        cd_refresh: bool = False,
    ) -> str:
        """Render a complete hook snippet for the given alias map.

        Only **enabled** aliases are included.  Output is sorted by name
        for stable generation.

        Platform-conditional aliases resolve *before* rendering: each
        alias is swapped for a copy whose ``command`` is the variant
        chosen by :meth:`Alias.resolve_command`, so ``render_alias`` —
        and therefore every renderer, including third-party plugin
        renderers — sees the platform-appropriate command without any
        signature change.

        When :attr:`supports_completions` is true, aliases carrying a
        ``complete`` mapping additionally emit their shell-native
        completion definitions after all alias definitions.

        With ``cd_refresh=True``, a renderer whose shell supports
        directory-change hooks (bash, zsh, fish) appends the footer that
        re-runs ``qwik init`` whenever the working directory changes —
        how the project layer (``.qwik.toml``) stays live as the user
        moves in and out of the project tree.

        Args:
            aliases: The alias map to render.
            platform: Platform to resolve for; defaults to the current host.
            shell: Shell to resolve for; defaults to this renderer's shell.
        """
        resolved_platform = platform or current_platform()
        resolved_shell = shell or self.shell_name
        complete_lines: list[str] = []
        lines: list[str] = []
        header = self.render_header()
        if header:
            lines.append(header)
        for name in sorted(aliases):
            alias = aliases[name]
            if alias.enabled:
                resolved = alias.resolve_command(resolved_platform, resolved_shell)
                if resolved != alias.command:
                    alias = alias.model_copy(update={"command": resolved})
                lines.append(self.render_alias(name, alias))
                if self.supports_completions and alias.complete:
                    definition = self.render_completion_alias(name, alias)
                    if definition:
                        complete_lines.append(definition)
        lines.extend(complete_lines)
        footer = self.render_footer()
        if footer:
            lines.append(footer)
        if cd_refresh:
            refresh = self.render_cd_refresh_footer()
            if refresh:
                lines.append(refresh)
        return "\n".join(lines)


def get_renderer(shell: str) -> ShellRenderer:
    """Return the concrete renderer for *shell*.

    Discovers renderers via the ``qwik.shell_renderers`` entry-point
    group, cached after the first call (see :func:`_renderer_registry`)
    rather than re-scanning entry points on every call.

    Raises:
        ValueError: If *shell* is not supported.
    """
    shell = shell.lower().strip()
    cls = _renderer_registry().get(shell)
    if cls is None:
        raise ValueError(f"Unsupported shell: {shell}. Choose from {supported_shells()}.")
    return cast("ShellRenderer", cls())
