"""Tests for the overlay add/update trust-boundary preview and git plumbing.

`qwik overlay add`/`update` used to pull and install remote commands with
no preview or confirmation — the only one of the three ingestion paths
(import, sync pull, overlay) without a gate — and built the overlay repo
with `git init` + `git remote add` + `git pull` instead of `git clone` /
`git fetch` + `git reset --hard`, which left no upstream tracking branch
and could enter a merge-conflict state on a diverged local tree.

These use a real local bare repo as the "remote" so the git plumbing
(clone, fetch, reset --hard) is exercised for real, not mocked.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
import tomlkit
from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git not installed"
)


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _make_remote(tmp_path: Path, aliases: dict[str, str]) -> Path:
    """Create a bare repo + a work clone, write aliases.toml, push to main."""
    remote = tmp_path / "team.git"
    _git(["init", "--bare", "-b", "main", str(remote)], tmp_path)

    work = tmp_path / "work"
    _git(["clone", str(remote), str(work)], tmp_path)
    _git(["checkout", "-b", "main"], work)
    _git(["config", "user.email", "test@example.com"], work)
    _git(["config", "user.name", "Test"], work)

    _write_aliases(work, aliases)
    _git(["add", "-A"], work)
    _git(["commit", "-m", "initial"], work)
    _git(["push", "-u", "origin", "main"], work)
    return remote


def _write_aliases(work: Path, aliases: dict[str, str]) -> None:
    doc = tomlkit.document()
    doc.add("version", 1)
    table = tomlkit.table()
    for name, command in aliases.items():
        t = tomlkit.table()
        t.add("command", command)
        table.add(name, t)
    doc.add("aliases", table)
    (work / "aliases.toml").write_text(tomlkit.dumps(doc), encoding="utf-8")


def _push_update(work: Path, aliases: dict[str, str]) -> None:
    _write_aliases(work, aliases)
    _git(["add", "-A"], work)
    _git(["commit", "-m", "update"], work)
    _git(["push"], work)


def _setup(tmp_path, monkeypatch):
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()


class TestOverlayAddPreview:
    def test_add_shows_preview_and_prompts(self, tmp_path, monkeypatch):
        _setup(tmp_path, monkeypatch)
        remote = _make_remote(tmp_path, {"teamalias": "echo team"})
        with patch("qwik.commands.importer.prompt_confirm", return_value=False) as c:
            result = runner.invoke(
                app, ["overlay", "add", "--url", str(remote), "--branch", "main"]
            )
        assert c.called
        assert result.exit_code == 0
        assert "teamalias" in result.output
        assert "trust boundary" in result.output.lower()

    def test_declining_add_leaves_no_partial_state(self, tmp_path, monkeypatch):
        _setup(tmp_path, monkeypatch)
        remote = _make_remote(tmp_path, {"teamalias": "echo team"})
        with patch("qwik.commands.importer.prompt_confirm", return_value=False):
            runner.invoke(
                app, ["overlay", "add", "--url", str(remote), "--branch", "main"]
            )
        assert not (tmp_path / "overlay.toml").exists()
        assert not (tmp_path / "overlay-repo").exists()

    def test_confirming_add_configures_overlay(self, tmp_path, monkeypatch):
        _setup(tmp_path, monkeypatch)
        remote = _make_remote(tmp_path, {"teamalias": "echo team"})
        result = runner.invoke(
            app, ["overlay", "add", "--url", str(remote), "--branch", "main", "--yes"]
        )
        assert result.exit_code == 0
        assert (tmp_path / "overlay.toml").exists()

        from qwik.core.store import get_store

        data = get_store().load()
        assert "teamalias" in data.overlay_aliases

    def test_add_uses_git_clone_not_init(self, tmp_path, monkeypatch):
        # A real `git clone` leaves an upstream tracking branch; `git
        # init` + `remote add` + `pull` (the old approach) does not.
        _setup(tmp_path, monkeypatch)
        remote = _make_remote(tmp_path, {"teamalias": "echo team"})
        runner.invoke(
            app, ["overlay", "add", "--url", str(remote), "--branch", "main", "--yes"]
        )
        overlay_repo = tmp_path / "overlay-repo"
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "main@{upstream}"],
            cwd=overlay_repo, capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "origin/main"

    def test_add_when_already_configured_errors(self, tmp_path, monkeypatch):
        _setup(tmp_path, monkeypatch)
        remote = _make_remote(tmp_path, {"teamalias": "echo team"})
        runner.invoke(
            app, ["overlay", "add", "--url", str(remote), "--branch", "main", "--yes"]
        )
        result = runner.invoke(
            app, ["overlay", "add", "--url", str(remote), "--branch", "main", "--yes"]
        )
        assert result.exit_code == 1
        assert "already configured" in result.output.lower()


class TestOverlayUpdatePreview:
    def _add(self, tmp_path, remote):
        return runner.invoke(
            app, ["overlay", "add", "--url", str(remote), "--branch", "main", "--yes"]
        )

    def test_no_changes_reports_up_to_date_without_prompting(
        self, tmp_path, monkeypatch
    ):
        _setup(tmp_path, monkeypatch)
        remote = _make_remote(tmp_path, {"a": "echo a"})
        self._add(tmp_path, remote)

        with patch("qwik.commands.overlay.prompt_confirm") as confirm:
            result = runner.invoke(app, ["overlay", "update"])
        assert not confirm.called
        assert result.exit_code == 0
        assert "up to date" in result.output.lower()

    def test_update_shows_added_changed_removed_and_prompts(
        self, tmp_path, monkeypatch
    ):
        _setup(tmp_path, monkeypatch)
        remote = _make_remote(tmp_path, {"a": "echo a", "b": "echo b"})
        self._add(tmp_path, remote)

        work = tmp_path / "work"
        _push_update(work, {"a": "echo a-changed", "c": "echo c"})  # b removed

        with patch("qwik.commands.overlay.prompt_confirm", return_value=False) as c:
            result = runner.invoke(app, ["overlay", "update"])
        assert c.called
        assert result.exit_code == 0
        assert "c" in result.output  # added
        assert "a" in result.output  # changed
        assert "b" in result.output  # removed
        assert "trust boundary" in result.output.lower()

    def test_declining_update_leaves_overlay_unchanged(self, tmp_path, monkeypatch):
        _setup(tmp_path, monkeypatch)
        remote = _make_remote(tmp_path, {"a": "echo a"})
        self._add(tmp_path, remote)

        work = tmp_path / "work"
        _push_update(work, {"a": "echo a", "newone": "echo new"})

        with patch("qwik.commands.overlay.prompt_confirm", return_value=False):
            runner.invoke(app, ["overlay", "update"])

        from qwik.core.store import get_store

        data = get_store().load()
        assert "newone" not in data.overlay_aliases

    def test_confirming_update_applies_changes(self, tmp_path, monkeypatch):
        _setup(tmp_path, monkeypatch)
        remote = _make_remote(tmp_path, {"a": "echo a"})
        self._add(tmp_path, remote)

        work = tmp_path / "work"
        _push_update(work, {"a": "echo a", "newone": "echo new"})

        result = runner.invoke(app, ["overlay", "update", "--yes"])
        assert result.exit_code == 0

        from qwik.core.store import get_store

        data = get_store().load()
        assert "newone" in data.overlay_aliases

    def test_update_yes_still_shows_trust_warning(self, tmp_path, monkeypatch):
        _setup(tmp_path, monkeypatch)
        remote = _make_remote(tmp_path, {"a": "echo a"})
        self._add(tmp_path, remote)
        work = tmp_path / "work"
        _push_update(work, {"a": "echo a", "newone": "echo new"})

        result = runner.invoke(app, ["overlay", "update", "--yes"])
        assert "trust boundary" in result.output.lower()

    def test_update_uses_hard_reset_not_merge(self, tmp_path, monkeypatch):
        # A diverged local tree (e.g. a stray local commit) must never
        # produce a merge conflict — the overlay is read-only, so a hard
        # reset to the remote branch is always correct.
        _setup(tmp_path, monkeypatch)
        remote = _make_remote(tmp_path, {"a": "echo a"})
        self._add(tmp_path, remote)

        overlay_repo = tmp_path / "overlay-repo"
        (overlay_repo / "stray.txt").write_text("local-only change")
        _git(["add", "-A"], overlay_repo)
        _git(["commit", "-m", "stray local commit"], overlay_repo)

        work = tmp_path / "work"
        _push_update(work, {"a": "echo a", "newone": "echo new"})

        result = runner.invoke(app, ["overlay", "update", "--yes"])
        assert result.exit_code == 0
        assert "conflict" not in result.output.lower()
        assert not (overlay_repo / "stray.txt").exists()
