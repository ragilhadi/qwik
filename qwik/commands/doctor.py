"""``qwik doctor`` — diagnose environment and store health.

The inline check sequence of the original doctor is restructured into a
list of :class:`Check` objects, each with an ``id``, a ``run()`` and an
optional ``fix()``. The printed report is one renderer over that list;
``--json`` is another; ``--fix`` applies the safe repairs.

Exit codes: ``0`` clean or all-fixed, ``1`` unfixed errors remain, ``2``
a fix attempt itself failed.
"""

from __future__ import annotations

import json
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

import typer

from qwik.commands.sync import _load_sync_config
from qwik.config import get_config
from qwik.core.git import (
    _run_git,
    behind_ahead,
    current_branch,
    git_available,
    is_dirty,
)
from qwik.core.locking import FileLock, remove_stale_lock
from qwik.core.models import AliasStore
from qwik.core.shell_detect import (
    detect_shell,
    shell_name_from_env,
    shell_name_from_proc,
)
from qwik.core.store import (
    backup_sort_key,
    get_store,
    read_backup_text,
)
from qwik.shells.base import supported_shells
from qwik.ui.prompts import (
    print_error,
    print_success,
    print_warning,
    prompt_confirm,
)
from qwik.ui.theme import get_console

if TYPE_CHECKING:
    from pathlib import Path

    from rich.console import Console

    from qwik.core.store import Store

__all__ = [
    "CheckResult",
    "doctor_command",
    "latest_valid_backup",
]

# Backwards-compatible aliases for the pre-refactor private names.
_detect_shell = detect_shell
_shell_name_from_env = shell_name_from_env
_shell_name_from_proc = shell_name_from_proc
_backup_sort_key = backup_sort_key
_read_backup_text = read_backup_text

Status = Literal["ok", "warn", "error"]

# Temp files younger than this are assumed to belong to a live concurrent
# write, not debris from a crash.
_TMP_GRACE_SECONDS = 300


def _parse_toml_dict(raw: str) -> dict[str, Any]:
    """Parse TOML *raw* into an unwrapped dict (backup helper)."""
    import tomlkit

    return dict(tomlkit.parse(raw).unwrap())


def latest_valid_backup(backup_dir: Path) -> Path | None:
    """Return the newest valid backup TOML in *backup_dir*, or ``None``.

    Backups are named ``aliases-<stamp>.toml`` where ``<stamp>`` is a
    UTC timestamp with microseconds and a per-process monotonic counter
    (see :func:`qwik.core.store._now_stamp`), compared numerically by
    :func:`qwik.core.store.backup_sort_key` rather than as raw filename
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
    candidates = sorted(backup_dir.glob("aliases-*.toml"), key=backup_sort_key, reverse=True)
    for path in candidates:
        try:
            AliasStore.model_validate(_parse_toml_dict(read_backup_text(path)))
        except Exception:
            continue
        return path
    return None


_latest_valid_backup = latest_valid_backup


@dataclass
class CheckResult:
    """Outcome of one doctor check.

    Attributes:
        id: Stable identifier (e.g. ``store.readable``) usable by tooling.
        status: ``ok``, ``warn``, or ``error``.
        message: Human-readable finding (no Rich markup in JSON mode).
        fixable: Whether the check's ``fix()`` can repair this finding.
        fix_id: Machine-readable fix identifier (e.g. ``restore-backup``).
        detail: Extra machine-readable fields for the JSON output.
    """

    id: str
    status: Status
    message: str
    fixable: bool = False
    fix_id: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


class Check(ABC):
    """One diagnosable, optionally repairable aspect of the environment.

    Subclasses implement :meth:`run` to produce a :class:`CheckResult`;
    any state :meth:`fix` needs is stashed on the instance while running.
    """

    id: str

    @abstractmethod
    def run(self) -> CheckResult:
        """Execute the check and return its result."""
        ...

    def fix(self, *, console: Console, assume_yes: bool) -> bool:
        """Attempt the repair; return ``True`` when it succeeded.

        Repairs never modify an alias command or name — only
        environment/infrastructure state (restore from backup, remove
        debris, hook install, git reset of a read-only mirror).
        """
        print_error(f"No automatic fix available for '{self.id}'.", console=console)
        return False


class ShellCheck(Check):
    """Detect the current shell and report its support level."""

    id = "shell.detected"

    def __init__(self) -> None:
        self.shell: str | None = None

    def run(self) -> CheckResult:
        self.shell = _detect_shell()
        supported = supported_shells()
        if self.shell in supported:
            return CheckResult(
                self.id,
                "ok",
                f"{self.shell} is supported.",
                detail={"shell": self.shell, "supported": True},
            )
        if self.shell:
            return CheckResult(
                self.id,
                "warn",
                f"{self.shell}'s support is best-effort.",
                detail={"shell": self.shell, "supported": False},
            )
        return CheckResult(self.id, "warn", "Could not detect shell.", detail={"shell": None})


class HookCheck(Check):
    """Verify the qwik hook is present in the shell's rc file."""

    id = "shell.hook"

    def __init__(self) -> None:
        self.installed = False
        self.shell: str | None = None

    def run(self) -> CheckResult:
        self.shell = _detect_shell()
        self.installed = _hook_installed(self.shell)
        if self.installed:
            return CheckResult(self.id, "ok", "Shell hook appears installed.")
        if self.shell is not None:
            return CheckResult(
                self.id,
                "warn",
                f"Shell hook not detected. Run `qwik init {self.shell} --install`.",
                fixable=True,
                fix_id="install-hook",
                detail={"shell": self.shell},
            )
        return CheckResult(self.id, "warn", "Shell hook not detected (could not detect shell).")

    def fix(self, *, console: Console, assume_yes: bool) -> bool:
        shell = self.shell
        if shell is None:
            return False
        if not assume_yes and not prompt_confirm(
            f"Run `qwik init {shell} --install` now?", default=False, console=console
        ):
            return False
        from qwik.commands.init_shell import init_shell_command

        try:
            init_shell_command(shell=shell, install=True)
            return True
        except typer.Exit as exc:
            if exc.exit_code == 0:
                return True
            print_error(f"Hook install failed (exit {exc.exit_code}).", console=console)
            return False
        except Exception as exc:
            print_error(f"Hook install failed: {exc}", console=console)
            return False


class StoreCheck(Check):
    """Read the alias store; on failure, offer restoring the newest backup."""

    id = "store.readable"

    def __init__(self, store: Store) -> None:
        self._store = store
        self.backup_path: Path | None = None
        self.backup_count: int = 0

    def run(self) -> CheckResult:
        try:
            data = self._store.load()
        except Exception as exc:
            self.backup_path = latest_valid_backup(get_config().backup_dir)
            if self.backup_path is None:
                return CheckResult(
                    self.id,
                    "error",
                    f"Store unreadable: {exc}",
                    detail={"error": str(exc)},
                )
            parsed = _load_backup_store(self.backup_path)
            if parsed is not None:
                self.backup_count = len(parsed.aliases)
            return CheckResult(
                self.id,
                "error",
                f"Store unreadable: {exc}",
                fixable=True,
                fix_id="restore-backup",
                detail={"backup": self.backup_path.name},
            )
        return CheckResult(self.id, "ok", f"Store readable ({len(data.aliases)} aliases).")

    def fix(self, *, console: Console, assume_yes: bool) -> bool:
        backup = self.backup_path
        if backup is None:
            print_error(
                f"No valid backup found in {get_config().backup_dir}. Recover manually "
                "from an external copy, or rerun after placing a valid aliases-*.toml "
                "in that directory.",
                console=console,
            )
            return False
        if not assume_yes and not prompt_confirm(
            f"Restore from latest valid backup ({backup.name}, {self.backup_count} aliases)?",
            default=False,
            console=console,
        ):
            print_error(
                "Restore declined. Repair manually or rerun `qwik doctor`.",
                console=console,
            )
            return False
        try:
            self._store.restore(backup)
        except RuntimeError as exc:
            print_error(f"Restore failed: {exc}", console=console)
            return False
        print_success(
            f"Restored store from {backup.name} ({self.backup_count} aliases).",
            console=console,
        )
        return True


class ConflictCheck(Check):
    """Report aliases that shadow binaries on ``$PATH``.

    Deliberately never auto-fixed: shadowing changes command resolution,
    which is exactly what an automatic repair must not do. These stay
    warnings.
    """

    id = "aliases.conflicts"

    def __init__(self, store: Store) -> None:
        self._store = store

    def run(self) -> CheckResult:
        try:
            data = self._store.load()
        except Exception:
            # The store check already reported the unreadable store; this
            # check simply has nothing to add.
            return CheckResult(self.id, "ok", "Skipped (store unreadable).")
        if not data.aliases:
            return CheckResult(self.id, "ok", "No aliases — nothing to shadow.")
        conflicts = sorted(n for n in data.aliases if shutil.which(n))
        if conflicts:
            return CheckResult(
                self.id,
                "warn",
                f"Aliases shadowing PATH binaries: {', '.join(conflicts)}",
                detail={"conflicts": conflicts},
            )
        return CheckResult(self.id, "ok", "No alias shadows a system binary.")


class SyncRepoCheck(Check):
    """Report sync-repo state (branch, remote, dirty, ahead/behind)."""

    id = "sync.repo"

    def __init__(self) -> None:
        self.repo_dir: Path | None = None

    def run(self) -> CheckResult:
        config = get_config()
        self.repo_dir = config.sync_repo_dir
        if not (self.repo_dir / ".git").exists():
            return CheckResult(self.id, "ok", "Sync repo: not initialized.")
        try:
            branch = current_branch(self.repo_dir)
            dirty = is_dirty(self.repo_dir)
            remote_url, _ = _load_sync_config(self.repo_dir)
            remote_str = remote_url if remote_url is not None else "<not set>"
            try:
                behind, ahead = behind_ahead(self.repo_dir, "origin", branch)
                ahead_behind = f", {ahead} ahead / {behind} behind"
            except RuntimeError:
                ahead_behind = ""
            detail = {"branch": branch, "dirty": dirty}
            if dirty:
                return CheckResult(
                    self.id,
                    "warn",
                    f"Sync repo has uncommitted changes ({branch}, "
                    f"remote={remote_str}{ahead_behind}).",
                    detail=detail,
                )
            return CheckResult(
                self.id,
                "ok",
                f"Sync repo: configured ({branch}, remote={remote_str}{ahead_behind}).",
                detail=detail,
            )
        except RuntimeError as exc:
            return CheckResult(self.id, "warn", f"Sync repo present but unreadable: {exc}")


class GitAvailableCheck(Check):
    """git on PATH (needed by ``qwik sync`` / ``qwik overlay``)."""

    id = "git.available"

    def run(self) -> CheckResult:
        if git_available():
            return CheckResult(self.id, "ok", "git found on PATH.")
        return CheckResult(self.id, "warn", "git not found on PATH — `qwik sync` will not work.")


class StaleLockCheck(Check):
    """Detect a store lock file no live process holds (crash debris)."""

    id = "store.lock_stale"

    def __init__(self, store: Store) -> None:
        self._lock_path: Path = store.path.with_suffix(".toml.lock")
        self._stale = False

    def run(self) -> CheckResult:
        if not self._lock_path.exists():
            return CheckResult(self.id, "ok", "Store lock file absent.")
        try:
            held = _lock_is_held(self._lock_path)
        except OSError:
            return CheckResult(self.id, "ok", "Lock file unreadable; assuming live.")
        if held:
            return CheckResult(self.id, "ok", "Store lock is held by a live process.")
        self._stale = True
        return CheckResult(
            self.id,
            "warn",
            f"Stale lock file {self._lock_path.name} (no live holder).",
            fixable=True,
            fix_id="remove-stale-lock",
        )

    def fix(self, *, console: Console, assume_yes: bool) -> bool:
        if remove_stale_lock(self._lock_path):
            print_success("Removed stale lock file.", console=console)
            return True
        print_warning(f"Could not remove {self._lock_path}.", console=console)
        return False


class TempDebrisCheck(Check):
    """Remove orphaned ``aliases.toml.tmp-*`` files from a crashed write."""

    id = "store.tmp_debris"

    def __init__(self, store: Store) -> None:
        self._store = store
        self._debris: list[Path] = []

    def run(self) -> CheckResult:
        parent = self._store.path.parent
        if not parent.exists():
            return CheckResult(self.id, "ok", "No orphaned temp files.")
        import time

        now = time.time()
        debris: list[Path] = []
        for p in sorted(parent.glob(f"{self._store.path.name}.tmp-*")):
            try:
                if now - p.stat().st_mtime > _TMP_GRACE_SECONDS:
                    debris.append(p)
            except OSError:
                continue
        self._debris = debris
        if debris:
            names = ", ".join(p.name for p in debris)
            return CheckResult(
                self.id,
                "warn",
                f"Orphaned temp files from an interrupted write: {names}",
                fixable=True,
                fix_id="remove-tmp-debris",
                detail={"files": [p.name for p in debris]},
            )
        return CheckResult(self.id, "ok", "No orphaned temp files.")

    def fix(self, *, console: Console, assume_yes: bool) -> bool:
        removed = 0
        for p in self._debris:
            try:
                p.unlink(missing_ok=True)
                removed += 1
            except OSError:
                print_warning(f"Could not remove {p.name}.", console=console)
        if removed:
            print_success(f"Removed {removed} orphaned temp file(s).", console=console)
            return True
        return False


class OverlayRepoCheck(Check):
    """Detect an overlay repo stuck in a merge/conflict state."""

    id = "overlay.repo_state"

    def __init__(self) -> None:
        self.repo_dir: Path | None = None
        self.branch: str = "main"

    def run(self) -> CheckResult:
        config = get_config()
        repo = config.overlay_repo_dir
        self.repo_dir = repo
        if not (repo / ".git").exists():
            return CheckResult(self.id, "ok", "Overlay repo: not configured.")
        if not git_available():
            return CheckResult(self.id, "ok", "Skipped (git unavailable).")
        try:
            in_merge = _merge_state_present(repo)
        except RuntimeError as exc:
            return CheckResult(self.id, "warn", f"Overlay repo unreadable: {exc}")
        if not in_merge:
            return CheckResult(self.id, "ok", "Overlay repo: clean.")
        return CheckResult(
            self.id,
            "error",
            "Overlay repo is in a merge/conflict state.",
            fixable=True,
            fix_id="reset-overlay",
            detail={"repo": str(repo)},
        )

    def fix(self, *, console: Console, assume_yes: bool) -> bool:
        repo = self.repo_dir
        if repo is None:
            return False
        config_file = get_config().overlay_config_file
        if config_file.exists():
            from qwik.commands.overlay import _load_overlay_config

            _url, self.branch, _auto = _load_overlay_config(config_file)
        if not assume_yes and not prompt_confirm(
            f"Reset overlay repo to origin/{self.branch}?", default=False, console=console
        ):
            return False
        from qwik.core.git import reset_hard

        try:
            reset_hard(repo, f"origin/{self.branch}")
        except RuntimeError as exc:
            print_error(f"Failed to reset overlay repo: {exc}", console=console)
            return False
        print_success(f"Overlay repo reset to origin/{self.branch}.", console=console)
        return True


# --- helpers ----------------------------------------------------------------


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


def _lock_is_held(path: Path) -> bool:
    """Return ``True`` when *path* exists and a live process holds its lock."""
    if not path.exists():
        return False
    lock = FileLock(path)
    try:
        lock.acquire(timeout=0.2)
    except OSError:
        return True
    lock.release()
    return False


def _merge_state_present(repo: Path) -> bool:
    """Return ``True`` when *repo* has MERGE_HEAD or unmerged index entries."""
    try:
        _run_git(["rev-parse", "-q", "--verify", "MERGE_HEAD"], repo)
        return True
    except RuntimeError:
        pass
    return _run_git(["diff", "--name-only", "--diff-filter=U"], repo) != ""


def _load_backup_store(path: Path) -> AliasStore | None:
    """Parse a backup file into an :class:`AliasStore`, ``None`` if corrupt."""
    try:
        return AliasStore.model_validate(_parse_toml_dict(read_backup_text(path)))
    except Exception:
        return None


def _check_list(store: Store) -> list[Check]:
    """Return the standard doctor checks in report order."""
    return [
        ShellCheck(),
        HookCheck(),
        StoreCheck(store),
        StaleLockCheck(store),
        TempDebrisCheck(store),
        ConflictCheck(store),
        SyncRepoCheck(),
        GitAvailableCheck(),
        OverlayRepoCheck(),
    ]


def doctor_command(
    fix: bool = typer.Option(False, "--fix", help="Apply safe repairs where possible."),
    assume_yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation for --fix."),
    json_output: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON (no markup); always exit 0."
    ),
) -> None:
    """Diagnose shell, hook status, store health, conflicts, and sync repo.

    Without ``--fix`` the command only reports (plus the legacy interactive
    restore offer when the store is unreadable and a backup exists). With
    ``--fix`` it applies the safe repairs: restore the store from backup,
    remove a stale lock file, remove crashed temp files, reset the overlay
    repo, and install the hook (with a prompt unless ``--yes``). Anything
    that could shadow a binary or change an alias command is never
    auto-fixed. ``--json`` never prompts and always exits 0.
    """
    console = get_console()
    store = get_store()
    checks = _check_list(store)

    results: list[CheckResult] = []
    fix_failed_on_error = False
    for check in checks:
        result = check.run()
        was_error = result.status == "error"
        # --fix repairs every fixable finding. The hook install edits an
        # rc file and prints its own output, so in --json mode (whose
        # stdout must stay machine-readable) it is only allowed with
        # --yes; stateless repairs (stale lock, tmp debris, restore,
        # git reset) run there regardless. Plain `qwik doctor` keeps its
        # legacy behavior: interactively offering the backup restore when
        # the store is unreadable — the exact path every error message
        # names. `--json` never prompts.
        hook_fix_in_json = check.id == "shell.hook" and json_output and not assume_yes
        if fix and result.fixable and not hook_fix_in_json:
            rerun = _apply_fix(check, result, console, assume_yes)
            if rerun is not None:
                result = rerun
        elif result.fixable and was_error and not fix and not json_output:
            if check.fix(console=console, assume_yes=False):
                result = check.run()
        # A fixable error that persists (declined, failed, or blocked in
        # JSON mode) means --fix could not fully repair: exit 2. A
        # non-fixable error keeps the classic exit 1.
        if fix and was_error and result.status == "error" and result.fixable:
            fix_failed_on_error = True
        results.append(result)

    if json_output:
        _emit_json(results, console)
        return

    _render_report(results, console)

    errors = sum(1 for r in results if r.status == "error")
    if fix and fix_failed_on_error:
        raise typer.Exit(2)
    if errors:
        raise typer.Exit(1)


def _apply_fix(
    check: Check,
    result: CheckResult,
    console: Console,
    assume_yes: bool,
) -> CheckResult | None:
    """Run *check*'s fix; return the re-run result, or ``None`` on refusal."""
    fixed = check.fix(console=console, assume_yes=assume_yes)
    if not fixed:
        return None
    return check.run()


def _render_report(results: list[CheckResult], console: Console) -> None:
    """Print the classic doctor report from the check results."""
    ok = sum(1 for r in results if r.status == "ok")
    warn = sum(1 for r in results if r.status == "warn")
    err = sum(1 for r in results if r.status == "error")

    for r in results:
        if r.id == "shell.detected":
            shell = r.detail.get("shell")
            console.print(f"[bold]Shell detected:[/bold] {shell or 'unknown'}")
        if r.status == "ok":
            print_success(r.message, console=console)
        elif r.status == "warn":
            print_warning(r.message, console=console)
        else:
            print_error(r.message, console=console)

    console.print()
    total = ok + warn + err
    console.print(f"[bold]Summary:[/bold] {ok}/{total} passed, {warn} warning(s), {err} error(s)")


def _emit_json(results: list[CheckResult], console: Console) -> None:
    """Print the machine-readable findings; never prompts, always exit 0."""
    payload: dict[str, Any] = {
        "status": (
            "ok"
            if all(r.status == "ok" for r in results)
            else ("error" if any(r.status == "error" for r in results) else "warn")
        ),
        "checks": [
            {
                "id": r.id,
                "status": r.status,
                "message": r.message,
                "fixable": r.fixable,
                **({"fix": r.fix_id} if r.fix_id is not None else {}),
                **({"detail": r.detail} if r.detail else {}),
            }
            for r in results
        ],
        "summary": {
            "ok": sum(1 for r in results if r.status == "ok"),
            "warn": sum(1 for r in results if r.status == "warn"),
            "error": sum(1 for r in results if r.status == "error"),
        },
    }
    console.print_json(json.dumps(payload))
