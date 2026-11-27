"""PowerShell shell hook renderer."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from qwik.shells.base import ShellRenderer

if TYPE_CHECKING:
    from qwik.core.models import Alias

__all__ = ["PwshRenderer"]


class PwshRenderer(ShellRenderer):
    """Emit PowerShell function definitions."""

    supports_native_templates = True
    supports_completions = True

    @property
    def shell_name(self) -> str:
        """Return ``'pwsh'``."""
        return "pwsh"

    def render_alias(self, name: str, alias: Alias) -> str:
        """Return a PowerShell function definition.

        All aliases are rendered as functions because PowerShell does not
        support passing arbitrary arguments to native ``alias``.
        Template mode references PowerShell's own ``$args``/``@args``
        machinery where the placeholder grammar translates natively,
        falling back to ``qwik run`` for constructs it cannot express
        (e.g. ``{*}``'s space-joined single string).  Append mode wraps
        the command as a single-quoted string literal compiled into a
        script block at call time, so the raw command text is never
        spliced into the function body as source — a ``}`` (or any other
        PowerShell syntax) inside it can't close the function early.

        Args:
            name: Alias identifier.
            alias: The alias definition.

        Returns:
            PowerShell source snippet.
        """
        from qwik.core.substitute import has_placeholders, render_native

        if has_placeholders(alias.command):
            native = render_native(alias.command, "pwsh")
            if native is not None:
                return f"function {name} {{\n    {native}\n}}"
            return f'function {name} {{\n    qwik run "{name}" @args\n}}'
        escaped = alias.command.replace("'", "''")
        return f"function {name} {{\n    & ([ScriptBlock]::Create('{escaped}')) @args\n}}"

    def render_completion_alias(self, name: str, alias: Alias) -> str:
        """Return the pwsh completion definition for *name*, if declared."""
        from qwik.shells.completions import pwsh_completion

        return pwsh_completion(name, alias)

    def rc_path(self) -> Path | None:
        """Return the PowerShell profile path, Windows-aware."""
        if sys.platform == "win32":
            userprofile = os.environ.get("USERPROFILE")
            docs = Path(userprofile) if userprofile else Path.home()
            try:
                import ctypes

                csidl_personal = 5
                buf = ctypes.create_unicode_buffer(260)
                ctypes.windll.shell32.SHGetFolderPathW(None, csidl_personal, None, 0, buf)
                pwsh_dir = Path(buf.value) / "PowerShell"
            except Exception:
                pwsh_dir = docs / "Documents" / "PowerShell"
        else:
            pwsh_dir = Path.home() / ".config" / "powershell"
        return pwsh_dir / "Microsoft.PowerShell_profile.ps1"

    def install_hook_line(self) -> str | None:
        """Return the PowerShell hook line."""
        return "\nInvoke-Expression (qwik init pwsh | Out-String)\n"
