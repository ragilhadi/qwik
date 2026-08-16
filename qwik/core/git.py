"""Thin subprocess wrappers around the ``git`` CLI for ``qwik sync``.

Shells out to ``git`` via :func:`subprocess.run` so the project does not
need a GitPython dependency.  Every function raises :class:`RuntimeError`
with an actionable message on failure (missing git binary or non-zero
git exit), letting callers surface errors via ``print_error``.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

__all__ = [
    "add_all_and_commit",
    "add_remote",
    "behind_ahead",
    "clone",
    "current_branch",
    "fetch",
    "get_remote_url",
    "git_available",
    "has_remote",
    "init_repo",
    "is_dirty",
    "pull",
    "push",
    "reset_hard",
    "status_short",
]


def git_available() -> bool:
    """Return ``True`` if a ``git`` executable is resolvable on ``PATH``."""
    return shutil.which("git") is not None


def _run_git(args: list[str], cwd: Path) -> str:
    """Run ``git <args>`` in *cwd* and return stripped stdout.

    Args:
        args: Git subcommand + flags (without the leading ``git``).
        cwd: Working tree to run in.

    Returns:
        Stripped stdout from git.

    Raises:
        RuntimeError: if git is missing or exits non-zero.
    """
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git not found on PATH. Install git or run 'qwik doctor'.") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"git {' '.join(args)} failed: {exc.stderr}") from exc
    return result.stdout.strip()


def init_repo(path: Path) -> None:
    """``git init`` inside *path*."""
    _run_git(["init"], path)


def is_dirty(path: Path) -> bool:
    """Return ``True`` if the working tree has uncommitted changes."""
    return _run_git(["status", "--porcelain"], path) != ""


def current_branch(path: Path) -> str:
    """Return the current branch name (``git rev-parse --abbrev-ref HEAD``)."""
    return _run_git(["rev-parse", "--abbrev-ref", "HEAD"], path)


def add_all_and_commit(path: Path, message: str) -> None:
    """Stage every change (``git add -A``) and commit with *message*."""
    _run_git(["add", "-A"], path)
    _run_git(["commit", "-m", message], path)


def has_remote(path: Path, name: str = "origin") -> bool:
    """Return ``True`` if a remote named *name* is configured."""
    remotes = _run_git(["remote"], path)
    return name in remotes.splitlines()


def add_remote(path: Path, url: str, name: str = "origin") -> None:
    """Add a remote named *name* pointing at *url*."""
    _run_git(["remote", "add", name, url], path)


def push(path: Path, remote: str, branch: str) -> None:
    """Push *branch* to *remote*."""
    _run_git(["push", remote, branch], path)


def pull(path: Path, remote: str, branch: str) -> None:
    """Pull *branch* from *remote*."""
    _run_git(["pull", remote, branch], path)


def clone(url: str, dest: Path, branch: str, *, depth: int | None = 1) -> None:
    """Clone *url* at *branch* into *dest* (``dest`` must not yet exist).

    Args:
        url: Remote repository URL.
        dest: Destination directory. Its parent must already exist;
            ``dest`` itself must not.
        branch: Branch to check out.
        depth: History depth to fetch (``git clone --depth``), or
            ``None`` for a full clone.
    """
    args = ["clone", "--branch", branch]
    if depth is not None:
        args += ["--depth", str(depth)]
    args += [url, str(dest)]
    _run_git(args, dest.parent)


def fetch(path: Path, remote: str, branch: str) -> None:
    """Fetch *branch* from *remote* without merging it."""
    _run_git(["fetch", remote, branch], path)


def reset_hard(path: Path, ref: str) -> None:
    """Hard-reset the working tree to *ref* (e.g. ``origin/main``)."""
    _run_git(["reset", "--hard", ref], path)


def show_file(path: Path, ref: str, file: str) -> str:
    """Return the contents of *file* at *ref* (``git show <ref>:<file>``).

    Reads the blob directly from git's object store without touching the
    working tree, so it can be used to preview incoming content (e.g.
    after a ``fetch``, before a ``reset --hard``) without applying it.

    Raises:
        RuntimeError: If *file* does not exist at *ref*.
    """
    return _run_git(["show", f"{ref}:{file}"], path)


def status_short(path: Path) -> str:
    """Return ``git status --short`` output (may be empty)."""
    return _run_git(["status", "--short"], path)


def get_remote_url(path: Path, name: str = "origin") -> str | None:
    """Return the URL of remote *name*, or ``None`` if it is not configured."""
    try:
        return _run_git(["remote", "get-url", name], path)
    except RuntimeError:
        return None


def behind_ahead(path: Path, remote: str, branch: str) -> tuple[int, int]:
    """Return ``(behind, ahead)`` counts for HEAD vs ``<remote>/<branch>``."""
    out = _run_git(
        ["rev-list", "--left-right", "--count", f"{remote}/{branch}...HEAD"],
        path,
    )
    parts = out.split()
    if len(parts) != 2:
        raise RuntimeError(f"could not parse ahead/behind from {out!r}")
    left, right = parts
    return int(left), int(right)
