"""``qwik doctor`` — diagnose environment and store health."""

from __future__ import annotations

import re
import shutil
import time
from pathlib import Path

import tomlkit
import typer

from qwik.commands.sync import _load_sync_config
from qwik.config import get_config
from qwik.core.git import behind_ahead, current_branch, git_available, is_dirty
from qwik.core.models import AliasStore
from qwik.core.shell_detect import (
    detect_shell,
    shell_name_from_env,
    shell_name_from_proc,
)
from qwik.core.store import get_store
from qwik.shells.base import supported_shells
from qwik.ui.prompts import (
    print_error,
    print_info,
    print_success,
    print_warning,
    prompt_confirm,
)
from qwik.ui.theme import get_console

__all__ = ["doctor_command"]

_detect_shell = detect_shell
_shell_name_from_env = shell_name_from_env
_shell_name_from_proc = shell_name_from_proc


_BACKUP_STAMP_RE = re.compile(r"^aliases-(\d{8})-(\d{6})-(\d{6})-(\d+)\.toml$")


def _backup_sort_key(path: Path) -> tuple[int, int, int, int]:
    """Parse a backup filename's stamp into a numerically comparable key.

    Sorting the filenames themselves as strings (the previous approach)
    silently breaks the moment the trailing counter's zero-padded width
    is exceeded — ``"...-9999"`` sorts *after* ``"...-10000"``
    lexicographically, the reverse of numeric order — reintroducing
    exactly the collision the counter exists to prevent. Parsing each
    field and comparing as integers has no such width dependency.
    Anything not matching the expected shape (e.g. a hand-placed or
    corrupt file) sorts as the oldest possible entry rather than
    erroring, since :func:`_latest_valid_backup` already validates
    content separately.
    """
    match = _BACKUP_STAMP_RE.match(path.name)
    if match is None:
        return (0, 0, 0, 0)
    date, clock, micros, counter = match.groups()
    return (int(date), int(clock), int(micros), int(counter))


def _read_backup_text(path: Path) -> str:
    """Read *path*, retrying briefly on a transient Windows file lock.

    A backup file is written moments before this reads it back, and on
    Windows a just-created file can be held open for a short window by
    antivirus real-time scanning or the search indexer — long enough for
    a same-process read immediately afterward to see ``PermissionError``
    (WinError 32) even though nothing in *this* process still has it
    open. POSIX never raises for this case, so the loop costs nothing
    there beyond the (never-taken) first attempt.
    """
    delay = 0.05
    for attempt in range(5):
        try:
            return path.read_text(encoding="utf-8")
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(delay)
            delay *= 2
    raise AssertionError("unreachable")  # pragma: no cover


def _latest_valid_backup(backup_dir: Path) -> Path | None:
    """Return the newest valid backup TOML in *backup_dir*, or ``None``.

    Backups are named ``aliases-<stamp>.toml`` where ``<stamp>`` is a
    UTC timestamp with microseconds and a per-process monotonic counter
    (see :func:`qwik.core.store._now_stamp`), parsed and compared
    numerically by :func:`_backup_sort_key` rather than as raw filename
    strings — more reliable than ``st_mtime`` too, which has coarse
    resolution on some filesystems (Windows ~15 ms).

    Args:
        backup_dir: Directory holding backup files.

    Returns:
        The :class:`~pathlib.Path` of the newest valid backup, or ``None``
        if none validate (or the directory is empty/missing).
    """
    if not backup_dir.exists():
        return None
    candidates = sorted(backup_dir.glob("aliases-*.toml"), key=_backup_sort_key, reverse=True)
    for path in candidates:
        try:
            doc = tomlkit.parse(_read_backup_text(path))
            AliasStore.model_validate(doc.unwrap())
        except Exception:
            continue
        return path
    return None


def doctor_command() -> None:
    """Diagnose shell, hook status, store readability, and conflicts."""
    console = get_console()
    store = get_store()

    checks_ok = 0
    checks_warn = 0
    checks_err = 0

    # Detect shell
    shell = _detect_shell()
    console.print(f"[bold]Shell detected:[/bold] {shell or 'unknown'}")
    if shell in supported_shells():
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
        backup_dir = get_config().backup_dir
        backup = _latest_valid_backup(backup_dir)
        if backup is None:
            print_error(
                f"No valid backup found in {backup_dir}. Recover manually from an "
                "external copy, or rerun after placing a valid aliases-*.toml in "
                "that directory.",
                console=console,
            )
        else:
            try:
                backup_store = AliasStore.model_validate(
                    tomlkit.parse(_read_backup_text(backup)).unwrap()
                )
                count = len(backup_store.aliases)
            except Exception:
                print_error(
                    f"Could not read backup {backup.name}.",
                    console=console,
                )
            else:
                if prompt_confirm(
                    f"Restore from latest valid backup ({backup.name}, {count} aliases)?",
                    default=False,
                    console=console,
                ):
                    shutil.copy2(backup, store.path)
                    data = store.load()
                    print_success(
                        f"Restored store from {backup.name} ({count} aliases).",
                        console=console,
                    )
                    checks_err -= 1
                    checks_ok += 1
                else:
                    print_error(
                        "Restore declined. Repair manually or rerun `qwik doctor`.",
                        console=console,
                    )

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

    # Sync repo status
    config = get_config()
    sync_repo = config.sync_repo_dir
    if (sync_repo / ".git").exists():
        try:
            branch = current_branch(sync_repo)
            dirty = is_dirty(sync_repo)
            remote_url, _ = _load_sync_config(sync_repo)
            remote_str = remote_url if remote_url is not None else "<not set>"
            try:
                behind, ahead = behind_ahead(sync_repo, "origin", branch)
                ahead_behind_str = f", {ahead} ahead / {behind} behind"
            except RuntimeError:
                ahead_behind_str = ""
            print_success(
                f"Sync repo: configured ({branch}, remote={remote_str}{ahead_behind_str}).",
                console=console,
            )
            if dirty:
                print_warning("Sync repo has uncommitted changes.", console=console)
                checks_warn += 1
            else:
                checks_ok += 1
        except RuntimeError as exc:
            print_warning(f"Sync repo present but unreadable: {exc}", console=console)
            checks_warn += 1
    else:
        print_info("Sync repo: not initialized.", console=console)
        checks_ok += 1

    if not git_available():
        print_warning(
            "git not found on PATH — `qwik sync` will not work.",
            console=console,
        )
        checks_warn += 1

    # Summary
    console.print()
    total = checks_ok + checks_warn + checks_err
    console.print(
        f"[bold]Summary:[/bold] {checks_ok}/{total} passed, "
        f"{checks_warn} warning(s), {checks_err} error(s)"
    )
    if checks_err:
        raise typer.Exit(1)


def _hook_installed(shell: str | None) -> bool:
    """Crude heuristic: grep rc file for 'qwik init'.

    Args:
        shell: Detected shell name.

    Returns:
        ``True`` if the rc file contains an ``qwik init`` invocation.
    """
    if shell is None:
        return False
    try:
        from qwik.shells.base import get_renderer

        rc = get_renderer(shell).rc_path()
    except ValueError:
        return False
    if rc is None or not rc.exists():
        return False
    try:
        return "qwik init" in rc.read_text(encoding="utf-8")
    except Exception:
        return False
