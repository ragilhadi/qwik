"""``qwik completion`` — print or install shell completion scripts."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console

from qwik.shells.base import get_renderer
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
    if shell == "zsh":
        # See _ZSH_MARKER_V1 below for why zsh's marker is versioned.
        return "# qwik completion (zsh) v2"
    return f"# qwik completion ({shell})"


def _backup(rc: Path, console: Console) -> None:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    backup = rc.parent / f"{rc.name}.qwik-backup-{stamp}"
    shutil.copy2(rc, backup)
    print_success(f"Backed up {rc} to {backup}", console=console)


def completion_command(
    shell: str = typer.Argument(..., help="Target shell: bash|zsh|fish|pwsh|powershell"),
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

    canonical = "pwsh" if shell in {"pwsh", "powershell"} else shell
    marker = _marker(canonical)

    if canonical == "bash":
        _install_bash(marker, console)
        print_info("Open a new terminal or run: source ~/.bashrc", console=console)
        raise typer.Exit(0)

    if canonical == "zsh":
        _install_zsh(marker, console)
        print_info("Open a new terminal or run: source ~/.zshrc", console=console)
        raise typer.Exit(0)

    if canonical == "fish":
        _install_fish(console)
        print_info("fish auto-loads completions on next shell start", console=console)
        raise typer.Exit(0)

    _install_pwsh(marker, console)
    print_info("Open a new PowerShell session to apply", console=console)
    raise typer.Exit(0)


def _install_bash(marker: str, console: Console) -> None:
    rc = get_renderer("bash").rc_path()
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
    # Write the path this install actually resolved and wrote to, not a
    # hardcoded `~/...` literal — the two only agree when rc.parent is
    # $HOME, which isn't guaranteed (e.g. $QWIK_CONFIG_DIR-style overrides
    # or a non-default rc location).
    source_line = f"\n{marker}\nsource {script_path}\n"
    with rc.open("a", encoding="utf-8") as fh:
        fh.write(source_line)
    print_success(f"Added source line to {rc}", console=console)


# v2: the v1 block appended a bare `compinit` with no `autoload -Uz
# compinit` first — compinit is an autoloadable function, not a builtin,
# so every new zsh session printed "command not found: compinit" and
# completions never activated. The marker is versioned so a rerun of
# `qwik completion zsh --install` detects and replaces a v1 block instead
# of reporting "already installed" and leaving the broken one in place.
_ZSH_MARKER_V1 = "# qwik completion (zsh)"


def _strip_legacy_zsh_block(rc_content: str) -> str:
    """Remove a v1 zsh completion block (marker + its 2 known lines)."""
    lines = rc_content.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() == _ZSH_MARKER_V1:
            # v1 always wrote exactly: marker, fpath line, compinit line
            # (see the pre-fix source), preceded by one blank line.
            j = i + 1
            while j < len(lines) and lines[j].strip() in (
                "fpath=($HOME/.zfunc $fpath)",
                "compinit",
            ):
                j += 1
            if out and out[-1].strip() == "":
                out.pop()
            i = j
            continue
        out.append(lines[i])
        i += 1
    return "".join(out)


def _install_zsh(marker: str, console: Console) -> None:
    rc = get_renderer("zsh").rc_path()
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
    # Line-exact match: `_ZSH_MARKER_V1` is a string-prefix of the v2
    # marker, so a naive `in` check would misfire on a file that only has
    # the v2 block.
    has_legacy = any(line.strip() == _ZSH_MARKER_V1 for line in rc_content.splitlines())
    if marker in rc_content and not has_legacy:
        print_info("already installed", console=console)
        return
    if rc.exists():
        _backup(rc, console)
    if has_legacy:
        rc_content = _strip_legacy_zsh_block(rc_content)
        rc.write_text(rc_content, encoding="utf-8")
        print_info("Repaired a previously broken compinit block.", console=console)
    # Guard against calling compinit a second time when the user's own
    # framework (oh-my-zsh, prezto) or a later line in their rc already
    # did — a second call is slow and can emit insecure-directory
    # warnings. `compdef` is only ever defined by a completed compinit run.
    hook_line = (
        f"\n{marker}\n"
        f"fpath=({script_path.parent} $fpath)\n"
        f"(( $+functions[compdef] )) || {{ autoload -Uz compinit; compinit; }}\n"
    )
    with rc.open("a", encoding="utf-8") as fh:
        fh.write(hook_line)
    print_success(f"Added fpath/compinit to {rc}", console=console)


def _install_fish(console: Console) -> None:
    rc = get_renderer("fish").rc_path()
    if rc is None:
        print_error("Cannot determine fish config directory.", console=console)
        raise typer.Exit(1)
    fish_dir = rc.parent
    script_path = fish_dir / "completions" / "qwik.fish"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(_get_script("fish"), encoding="utf-8")
    print_success(f"Wrote completion script to {script_path}", console=console)


def _install_pwsh(marker: str, console: Console) -> None:
    rc = get_renderer("pwsh").rc_path()
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
