"""``qwik init`` — emit or install shell hook snippets."""

from __future__ import annotations

import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console

from qwik.core.store import get_store
from qwik.shells.base import get_renderer
from qwik.ui.prompts import print_error, print_info, print_success

__all__ = ["init_shell_command"]


def _rc_path(shell: str) -> Path | None:
    """Guess the standard rc file for *shell*.

    Args:
        shell: Shell identifier.

    Returns:
        A :class:`~pathlib.Path` to the rc file, or ``None`` if unknown.
    """
    home = Path.home()
    if shell == "pwsh":
        pwsh_dir = home / ".config" / "powershell"
        if sys.platform == "win32":
            import os

            # Use %USERPROFILE%\Documents instead of hardcoded "Documents"
            # to support non-English Windows and relocated folders.
            docs = Path.home()
            userprofile = os.environ.get("USERPROFILE")
            if userprofile:
                docs = Path(userprofile)
            # Try to discover the localized Documents folder name via ctypes
            # (CSIDL 5 = My Documents). Falls back to "Documents".
            try:
                import ctypes

                csidl_personal = 5
                buf = ctypes.create_unicode_buffer(260)
                ctypes.windll.shell32.SHGetFolderPathW(
                    None, csidl_personal, None, 0, buf
                )
                pwsh_dir = Path(buf.value) / "PowerShell"
            except Exception:
                pwsh_dir = docs / "Documents" / "PowerShell"
        return pwsh_dir / "Microsoft.PowerShell_profile.ps1"
    mapping: dict[str, Path] = {
        "bash": home / ".bashrc",
        "zsh": home / ".zshrc",
        "fish": home / ".config" / "fish" / "config.fish",
    }
    return mapping.get(shell)


def init_shell_command(
    shell: str = typer.Argument(
        "bash", help="Target shell (bash, zsh, fish, pwsh, cmd)."
    ),
    install: bool = typer.Option(
        False, "--install", "-i", help="Append hook to rc file with backup."
    ),
) -> None:
    """Print or install the shell hook snippet."""
    store = get_store()
    data = store.load()
    console = Console()

    try:
        renderer = get_renderer(shell)
    except ValueError as exc:
        print_error(str(exc), console=console)
        raise typer.Exit(1)

    snippet = renderer.render_all(data.aliases)

    if not install:
        console.print(snippet)
        raise typer.Exit(0)

    rc = _rc_path(shell)
    if rc is None:
        print_error(f"Cannot determine rc file for {shell}.", console=console)
        raise typer.Exit(1)

    rc.parent.mkdir(parents=True, exist_ok=True)

    rc_content = rc.read_text(encoding="utf-8") if rc.exists() else ""

    hook_marker = f"# qwik shell hook ({shell})"
    if hook_marker in rc_content:
        print_info(f"Hook already present in {rc}.", console=console)
        print_info(f"Open a new terminal or run: source {rc}", console=console)
        raise typer.Exit(0)

    # Backup
    if rc.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup = rc.parent / f"{rc.name}.qwik-backup-{stamp}"
        shutil.copy2(rc, backup)
        print_success(f"Backed up {rc} to {backup}", console=console)

    hook_line = f'\n# qwik shell hook ({shell})\neval "$(qwik init {shell})"\n'
    if shell == "pwsh":
        hook_line = f"\n# qwik shell hook ({shell})\nInvoke-Expression (qwik init pwsh | Out-String)\n"
    elif shell == "fish":
        hook_line = f"\n# qwik shell hook ({shell})\nqwik init fish | source -\n"

    with rc.open("a", encoding="utf-8") as fh:
        fh.write(hook_line)

    print_success(f"Added hook to {rc}", console=console)
    print_info(f"Open a new terminal or run: source {rc}", console=console)
