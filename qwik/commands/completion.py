"""``qwik completion`` — print or install shell completion scripts."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console

from qwik.commands.init_shell import _fish_config_dir, _rc_path
from qwik.ui.prompts import print_error, print_info, print_success
from qwik.ui.theme import get_console

__all__ = ["completion_command"]

_PROG_NAME = "qwik"
_COMPLETE_VAR = "_QWIK_COMPLETE"

_VALID_SHELLS = {"bash", "zsh", "fish", "pwsh", "powershell"}


def _get_script(shell: str) -> str:
    """Return Typer's completion script for *shell*."""
    from typer._completion_shared import get_completion_script

    return get_completion_script(
        prog_name=_PROG_NAME,
        complete_var=_COMPLETE_VAR,
        shell=shell,
    )


def _marker(shell: str) -> str:
    return f"# qwik completion ({shell})"


def _backup(rc: Path, console: Console) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = rc.parent / f"{rc.name}.qwik-backup-{stamp}"
    shutil.copy2(rc, backup)
    print_success(f"Backed up {rc} to {backup}", console=console)


def completion_command(
    shell: str = typer.Argument(
        ..., help="Target shell: bash|zsh|fish|pwsh|powershell"
    ),
    install: bool = typer.Option(
        False,
        "--install",
        "-i",
        help="Install completion script into shell rc + source line.",
    ),
) -> None:
    """Print or install the shell completion script for qwik."""
    console = get_console()

    if shell not in _VALID_SHELLS:
        print_error(
            f"Unknown shell: {shell}",
            suggestion="Valid shells: bash, zsh, fish, pwsh, powershell",
            console=console,
        )
        raise typer.Exit(1)

    if not install:
        console.print(_get_script(shell))
        raise typer.Exit(0)

    marker = _marker(shell)

    if shell == "bash":
        _install_bash(marker, console)
        print_info("Open a new terminal or run: source ~/.bashrc", console=console)
        raise typer.Exit(0)

    if shell == "zsh":
        _install_zsh(marker, console)
        print_info("Open a new terminal or run: source ~/.zshrc", console=console)
        raise typer.Exit(0)

    if shell == "fish":
        _install_fish(console)
        print_info(
            "fish auto-loads completions on next shell start", console=console
        )
        raise typer.Exit(0)

    _install_pwsh(marker, console)
    print_info("Open a new PowerShell session to apply", console=console)
    raise typer.Exit(0)


def _install_bash(marker: str, console: Console) -> None:
    rc = _rc_path("bash")
    if rc is None:
        print_error("Cannot determine rc file for bash.", console=console)
        raise typer.Exit(1)
    home = rc.parent
    script_path = home / ".bash_completions" / "qwik.sh"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(_get_script("bash"), encoding="utf-8")
    print_success(f"Wrote completion script to {script_path}", console=console)

    rc.parent.mkdir(parents=True, exist_ok=True)
    rc_content = rc.read_text(encoding="utf-8") if rc.exists() else ""
    if marker in rc_content:
        print_info("already installed", console=console)
        return
    if rc.exists():
        _backup(rc, console)
    source_line = f"\n{marker}\nsource ~/.bash_completions/qwik.sh\n"
    with rc.open("a", encoding="utf-8") as fh:
        fh.write(source_line)
    print_success(f"Added source line to {rc}", console=console)


def _install_zsh(marker: str, console: Console) -> None:
    rc = _rc_path("zsh")
    if rc is None:
        print_error("Cannot determine rc file for zsh.", console=console)
        raise typer.Exit(1)
    home = rc.parent
    script_path = home / ".zfunc" / "_qwik"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(_get_script("zsh"), encoding="utf-8")
    print_success(f"Wrote completion script to {script_path}", console=console)

    rc.parent.mkdir(parents=True, exist_ok=True)
    rc_content = rc.read_text(encoding="utf-8") if rc.exists() else ""
    if marker in rc_content:
        print_info("already installed", console=console)
        return
    if rc.exists():
        _backup(rc, console)
    hook_line = f"\n{marker}\nfpath=(~/.zfunc $fpath)\ncompinit\n"
    with rc.open("a", encoding="utf-8") as fh:
        fh.write(hook_line)
    print_success(f"Added fpath/compinit to {rc}", console=console)


def _install_fish(console: Console) -> None:
    fish_dir = _fish_config_dir()
    script_path = fish_dir / "completions" / "qwik.fish"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(_get_script("fish"), encoding="utf-8")
    print_success(f"Wrote completion script to {script_path}", console=console)


def _install_pwsh(marker: str, console: Console) -> None:
    rc = _rc_path("pwsh")
    if rc is None:
        print_error("Cannot determine PowerShell profile path.", console=console)
        raise typer.Exit(1)
    rc.parent.mkdir(parents=True, exist_ok=True)
    rc_content = rc.read_text(encoding="utf-8") if rc.exists() else ""
    if marker in rc_content:
        print_info("already installed", console=console)
        return
    if rc.exists():
        _backup(rc, console)
    block = f"\n{marker}\n{_get_script('powershell')}\n"
    with rc.open("a", encoding="utf-8") as fh:
        fh.write(block)
    print_success(f"Appended completion to {rc}", console=console)