"""Tests for the sync command (git-backed dotfile sharing)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import tomlkit
from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()


class FakeGit:
    """Records subprocess.run calls and returns canned stdout based on git args.

    Tests monkeypatch ``qwik.core.git.subprocess.run`` with ``fake.run``.
    The fake actually executes the real filesystem effects that matter for
    assertions (writing files is done by qwik code, not git), while git
    commands are no-ops that return canned stdout.
    """

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.dirty: bool = False
        self.ahead: int = 0
        self.behind: int = 0
        self.remotes: list[str] = []

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | str | None = None,
        capture_output: bool = False,
        text: bool = False,
        check: bool = False,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        # Record only git commands (first arg == "git")
        if args and args[0] == "git":
            self.calls.append(list(args))
            return self._dispatch(args, cwd)
        # Non-git subprocess calls (shouldn't happen in sync) pass through
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    def _dispatch(
        self, args: list[str], cwd: Path | str | None
    ) -> subprocess.CompletedProcess[str]:
        sub = args[1] if len(args) > 1 else ""
        stdout = ""
        cwd_path = Path(cwd) if cwd is not None else None
        if sub == "init":
            # `git init` creates a .git directory marker so the rest of the
            # sync code (which checks <repo>/.git) treats the repo as initialized.
            if cwd_path is not None:
                (cwd_path / ".git").mkdir(parents=True, exist_ok=True)
            stdout = ""
        elif sub == "status":
            # --porcelain / --short: empty = clean
            stdout = "M aliases.toml" if self.dirty else ""
        elif sub == "remote":
            # `git remote` lists configured remotes; `git remote add <name> <url>`
            # records one so a subsequent listing returns it.
            if len(args) >= 4 and args[2] == "add":
                self.remotes.append(args[3])
                stdout = ""
            else:
                stdout = "\n".join(self.remotes)
        elif sub == "rev-parse":
            # --abbrev-ref HEAD → "main"
            stdout = "main"
        elif sub == "rev-list":
            # --left-right --count origin/main...HEAD → "<behind>\t<ahead>"
            stdout = f"{self.behind}\t{self.ahead}"
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

    @property
    def git_calls(self) -> list[tuple[str, ...]]:
        return [tuple(c) for c in self.calls]


def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeGit:
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    fake = FakeGit()
    monkeypatch.setattr("qwik.core.git.subprocess.run", fake.run)
    return fake


def _make_dirty(fake: FakeGit) -> None:
    """Make subsequent git status calls report a dirty tree."""
    fake.dirty = True


class TestSyncInit:
    def test_sync_init_creates_repo(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _setup_env(tmp_path, monkeypatch)
        # add an alias so there's something to export
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["sync", "init"])
        assert result.exit_code == 0, result.output
        sync_repo = tmp_path / "qwik-sync"
        assert sync_repo.exists()
        assert (sync_repo / "aliases.toml").exists()
        # git init, add -A, commit were called
        subcommands = [c[1] for c in fake.git_calls]
        assert "init" in subcommands
        assert "add" in subcommands
        assert "commit" in subcommands

    def test_sync_init_with_remote(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _setup_env(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "gs", "git", "status"])
        url = "https://example.com/dotfiles.git"
        result = runner.invoke(app, ["sync", "init", "--remote", url])
        assert result.exit_code == 0, result.output
        sync_repo = tmp_path / "qwik-sync"
        sync_toml = sync_repo / "sync.toml"
        assert sync_toml.exists()
        parsed = tomlkit.parse(sync_toml.read_text(encoding="utf-8"))
        assert parsed["remote_url"] == url  # type: ignore[index]
        assert parsed["branch"] == "main"  # type: ignore[index]
        # remote add was called
        remotes = [c for c in fake.git_calls if c[1] == "remote"]
        assert any("add" in c for c in remotes)


class TestSyncPush:
    def test_sync_push(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _setup_env(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "gs", "git", "status"])
        # init with remote first
        url = "https://example.com/dot.git"
        runner.invoke(app, ["sync", "init", "--remote", url])
        fake.calls.clear()
        # add another alias then push
        runner.invoke(app, ["add", "gco", "git", "checkout"])
        # mark dirty so push commits
        _make_dirty(fake)
        result = runner.invoke(app, ["sync", "push"])
        assert result.exit_code == 0, result.output
        sync_repo = tmp_path / "qwik-sync"
        # aliases.toml contains both aliases
        parsed = tomlkit.parse((sync_repo / "aliases.toml").read_text(encoding="utf-8"))
        names = set(parsed["aliases"].unwrap().keys())  # type: ignore[attr-defined]
        assert {"gs", "gco"} <= names
        subcommands = [c[1] for c in fake.git_calls]
        assert "add" in subcommands
        assert "commit" in subcommands
        assert "push" in subcommands

    def test_sync_push_clean(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _setup_env(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "gs", "git", "status"])
        runner.invoke(app, ["sync", "init", "--remote", "https://example.com/d.git"])
        fake.calls.clear()
        # tree is clean (default fake) → nothing to push
        result = runner.invoke(app, ["sync", "push"])
        assert result.exit_code == 0, result.output
        assert "nothing to push" in result.output.lower()
        subcommands = [c[1] for c in fake.git_calls]
        assert "commit" not in subcommands
        assert "push" not in subcommands

    def test_sync_no_remote(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_env(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "gs", "git", "status"])
        # init without remote
        runner.invoke(app, ["sync", "init"])
        result = runner.invoke(app, ["sync", "push"])
        assert result.exit_code == 1
        assert "no remote" in result.output.lower() or "not configured" in result.output.lower()


class TestSyncPull:
    def test_sync_pull(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _setup_env(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "gs", "git", "status"])
        runner.invoke(app, ["sync", "init", "--remote", "https://example.com/d.git"])
        # simulate remote change: write a new aliases.toml into sync repo with extra alias
        sync_repo = tmp_path / "qwik-sync"
        new_alias = {
            "version": 1,
            "aliases": {
                "gs": {"command": "git status"},
                "gp": {"command": "git push"},
            },
        }
        doc = tomlkit.document()
        doc.add("version", 1)
        aliases = tomlkit.table()
        for name, body in new_alias["aliases"].items():  # type: ignore[union-attr]
            t = tomlkit.table()
            t.add("command", body["command"])  # type: ignore[index]
            aliases.add(name, t)
        doc.add("aliases", aliases)
        (sync_repo / "aliases.toml").write_text(tomlkit.dumps(doc), encoding="utf-8")
        # pull merges gp into live store
        result = runner.invoke(app, ["sync", "pull", "--yes"])
        assert result.exit_code == 0, result.output
        # live store has gp now
        live = tomlkit.parse((tmp_path / "aliases.toml").read_text(encoding="utf-8"))
        assert "gp" in live["aliases"].unwrap()  # type: ignore[attr-defined]
        # backup created
        assert any((tmp_path / "backups").glob("aliases-*.toml"))
        subcommands = [c[1] for c in fake.git_calls]
        assert "pull" in subcommands

    def test_sync_pull_reuses_import_merge(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _setup_env(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "gs", "git", "status"])
        runner.invoke(app, ["sync", "init", "--remote", "https://example.com/d.git"])
        # simulate remote change that CONFLICTS: same name, different command
        sync_repo = tmp_path / "qwik-sync"
        doc = tomlkit.document()
        doc.add("version", 1)
        aliases = tomlkit.table()
        t = tomlkit.table()
        t.add("command", "git status --short")
        aliases.add("gs", t)
        doc.add("aliases", aliases)
        (sync_repo / "aliases.toml").write_text(tomlkit.dumps(doc), encoding="utf-8")
        result = runner.invoke(app, ["sync", "pull", "--yes"])
        assert result.exit_code == 0, result.output
        # conflict reported (trust warning only shown without --yes)
        assert "Conflicts" in result.output
        # live store overwritten with incoming command
        live = tomlkit.parse((tmp_path / "aliases.toml").read_text(encoding="utf-8"))
        assert live["aliases"]["gs"]["command"] == "git status --short"  # type: ignore[index]


class TestSyncStatus:
    def test_sync_status(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _setup_env(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "gs", "git", "status"])
        runner.invoke(app, ["sync", "init", "--remote", "https://example.com/d.git"])
        result = runner.invoke(app, ["sync", "status"])
        assert result.exit_code == 0, result.output
        assert "main" in result.output
        assert "https://example.com/d.git" in result.output

    def test_sync_status_not_initialized(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_env(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["sync", "status"])
        assert result.exit_code == 0, result.output
        assert "not initialized" in result.output.lower()


class TestSyncNoGit:
    def test_sync_no_git(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        monkeypatch.setattr("qwik.commands.sync.git_available", lambda: False)
        result = runner.invoke(app, ["sync", "init"])
        assert result.exit_code == 1
        assert "git" in result.output.lower()


class TestSyncTrustBoundary:
    def test_sync_pull_trust_warning_without_yes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_env(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "gs", "git", "status"])
        runner.invoke(app, ["sync", "init", "--remote", "https://example.com/d.git"])
        sync_repo = tmp_path / "qwik-sync"
        doc = tomlkit.document()
        doc.add("version", 1)
        aliases = tomlkit.table()
        t = tomlkit.table()
        t.add("command", "rm -rf /tmp")
        aliases.add("danger", t)
        doc.add("aliases", aliases)
        (sync_repo / "aliases.toml").write_text(tomlkit.dumps(doc), encoding="utf-8")
        # Decline the prompt
        result = runner.invoke(app, ["sync", "pull"], input="n\n")
        assert "trust" in result.output.lower() or "shell=True" in result.output.lower()
        assert "rm -rf /tmp" in result.output
        # declined → live store unchanged
        live = tomlkit.parse((tmp_path / "aliases.toml").read_text(encoding="utf-8"))
        assert "danger" not in live["aliases"].unwrap()  # type: ignore[attr-defined]


class TestSyncStatusDirty:
    def test_sync_status_dirty_reports_changes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _setup_env(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "gs", "git", "status"])
        runner.invoke(app, ["sync", "init", "--remote", "https://example.com/d.git"])
        fake.dirty = True
        fake.ahead = 1
        fake.behind = 2
        result = runner.invoke(app, ["sync", "status"])
        assert result.exit_code == 0, result.output
        assert "dirty" in result.output.lower()
        assert "1 ahead" in result.output
        assert "2 behind" in result.output


class TestSyncErrorPaths:
    def test_sync_unknown_action(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_env(tmp_path, monkeypatch)
        result = runner.invoke(app, ["sync", "bogus"])
        assert result.exit_code == 1
        assert "Unknown sync action" in result.output

    def test_sync_push_without_init(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_env(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["sync", "push"])
        assert result.exit_code == 1
        assert "not initialized" in result.output.lower()

    def test_sync_pull_without_init(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_env(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["sync", "pull", "--yes"])
        assert result.exit_code == 1
        assert "not initialized" in result.output.lower()

    def test_sync_pull_no_remote(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_env(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "gs", "git", "status"])
        runner.invoke(app, ["sync", "init"])
        result = runner.invoke(app, ["sync", "pull", "--yes"])
        assert result.exit_code == 1
        assert "no remote" in result.output.lower() or "not configured" in result.output.lower()