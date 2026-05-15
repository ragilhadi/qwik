"""``qwik doctor`` — diagnose environment and store health."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import typer
from rich.console import Console

from qwik.core.store import get_store
from qwik.shells.base import SUPPORTED_SHELLS
from qwik.ui.prompts import print_error, print_success, print_warning

__all__ = ["doctor_command"]


def doctor_command() -> None:
    """Diagnose shell, hook status, store readability, and conflicts."""
    console = Console()
    store = get_store()

    checks_ok = 0
    checks_warn = 0
    checks_err = 0

    # Detect shell
    shell = _detect_shell()
    console.print(f"[bold]Shell detected:[/bold] {shell or 'unknown'}")
    if shell in SUPPORTED_SHELLS:
        print_success(f"{shell} is supported.", console=console)
        checks_ok += 1
    elif shell:
        print_warning(f"{shell} support is best-effort.", console=console)
        checks_warn += 1

    # Hook installed?
    hook_installed = _hook_installed(shell)
    if hook_installed:
        print_success("Shell hook appears installed.", console=console)
        checks_ok += 1
    else:
        print_warning(
            "Shell hook not detected. Run `qwik init <shell> --install`.",
            console=console,
        )
        checks_warn += 1

    # Store readable?
    data = None
    try:
        data = store.load()
        print_success(f"Store readable ({len(data.aliases)} aliases).", console=console)
        checks_ok += 1
    except Exception as exc:
        print_error(f"Store unreadable: {exc}", console=console)
        checks_err += 1

    # Conflicts with system commands
    if data is not None:
        if data.aliases:
            conflicts = [n for n in data.aliases if shutil.which(n)]
            if conflicts:
                print_warning(
                    f"Aliases shadowing PATH binaries: {', '.join(conflicts)}",
                    console=console,
                )
                checks_warn += 1
            else:
                print_success("No alias shadows a system binary.", console=console)
                checks_ok += 1
        else:
            print_success("No aliases — nothing to shadow.", console=console)
            checks_ok += 1

    # Summary
    console.print()
    total = checks_ok + checks_warn + checks_err
    console.print(
        f"[bold]Summary:[/bold] {checks_ok}/{total} passed, "
        f"{checks_warn} warning(s), {checks_err} error(s)"
    )
    if checks_err:
        raise typer.Exit(1)


def _detect_shell() -> str | None:
    """Attempt to detect the current user's shell.

    Returns:
        A lowercase shell name (e.g. ``bash``, ``zsh``), or ``None``.
    """
    # Prefer the $SHELL environment variable.
    shell_env = os.environ.get("SHELL", "").lower()
    if "bash" in shell_env:
        return "bash"
    if "zsh" in shell_env:
        return "zsh"
    if "fish" in shell_env:
        return "fish"
    if "pwsh" in shell_env or "powershell" in shell_env:
        return "pwsh"

    # Fallback: inspect parent process via /proc on Linux.
    try:
        with Path("/proc/self/status").open(encoding="utf-8") as f:
            for line in f:
                if line.startswith("PPid:"):
                    ppid = line.split()[1]
                    exe_link = Path(f"/proc/{ppid}/exe")
                    if exe_link.exists():
                        name = exe_link.resolve().name.lower()
                        if "bash" in name:
                            return "bash"
                        if "zsh" in name:
                            return "zsh"
                        if "fish" in name:
                            return "fish"
                        if "pwsh" in name or "powershell" in name:
                            return "pwsh"
    except Exception:
        pass
    return None


def _hook_installed(shell: str | None) -> bool:
    """Crude heuristic: grep rc file for 'qwik init'.

    Args:
        shell: Detected shell name.

    Returns:
        ``True`` if the rc file contains an ``qwik init`` invocation.
    """
    if shell is None:
        return False
    rc_map = {
        "bash": Path.home() / ".bashrc",
        "zsh": Path.home() / ".zshrc",
        "fish": Path.home() / ".config" / "fish" / "config.fish",
        "pwsh": Path.home()
        / ".config"
        / "powershell"
        / "Microsoft.PowerShell_profile.ps1",
    }
    rc = rc_map.get(shell)
    if rc is None or not rc.exists():
        return False
    try:
        return "qwik init" in rc.read_text(encoding="utf-8")
    except Exception:
        return False
