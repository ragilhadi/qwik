"""CLI-level rollback tests for destructive operations.

Each test seeds the store, runs a destructive command via the CLI,
asserts a new backup file appears, then corrupts the live store and
verifies ``qwik doctor`` restores the pre-operation state from that
backup.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import tomlkit
from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()


def _setup(tmp_path: Path, monkeypatch) -> Path:
    """Isolate config under ``tmp_path`` and return the backup directory."""
    from qwik.config import _reset_config, get_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    return get_config().backup_dir


def _backup_count(backup_dir: Path) -> int:
    return len(list(backup_dir.glob("aliases-*.toml")))


def _corrupt_store(tmp_path: Path) -> None:
    (tmp_path / "aliases.toml").write_text("garbage", encoding="utf-8")


def _restore_and_load(tmp_path: Path):
    """Run ``qwik doctor`` accepting the restore prompt; return the store."""
    from qwik.config import _reset_config
    from qwik.core.store import get_store

    _reset_config()
    result = runner.invoke(app, ["doctor"], input="y\n")
    assert result.exit_code == 0, result.output
    return get_store().load()


class TestRollbackRm:
    def test_rm_creates_backup_and_doctor_restores_pre_op(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        backup_dir = _setup(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "gs", "git", "status"])
        runner.invoke(app, ["add", "gp", "git", "push"])
        before = _backup_count(backup_dir)

        result = runner.invoke(app, ["rm", "gs", "--yes"])
        assert result.exit_code == 0, result.output
        after = _backup_count(backup_dir)
        assert after == before + 1

        _corrupt_store(tmp_path)
        data = _restore_and_load(tmp_path)
        assert "gs" in data.aliases
        assert "gp" in data.aliases


class TestRollbackRename:
    def test_rename_creates_backup_and_doctor_restores_pre_op(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        backup_dir = _setup(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "old", "git", "status"])
        before = _backup_count(backup_dir)

        result = runner.invoke(app, ["rename", "old", "new"])
        assert result.exit_code == 0, result.output
        after = _backup_count(backup_dir)
        assert after == before + 1

        _corrupt_store(tmp_path)
        data = _restore_and_load(tmp_path)
        assert "old" in data.aliases
        assert "new" not in data.aliases


class TestRollbackEdit:
    def test_edit_creates_backup_and_doctor_restores_pre_op(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        backup_dir = _setup(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "gs", "git", "status"])
        before = _backup_count(backup_dir)

        def fake_run(args, check=True):
            tmp = Path(args[1])
            text = tmp.read_text(encoding="utf-8")
            text = text.replace("command = 'git status'", "command = 'git log'")
            tmp.write_text(text, encoding="utf-8")
            return subprocess.CompletedProcess(args=args, returncode=0)

        monkeypatch.setattr("qwik.commands.edit.subprocess.run", fake_run)
        result = runner.invoke(app, ["edit", "gs"])
        assert result.exit_code == 0, result.output
        after = _backup_count(backup_dir)
        assert after == before + 1

        _corrupt_store(tmp_path)
        data = _restore_and_load(tmp_path)
        assert "gs" in data.aliases
        assert data.aliases["gs"].command == "git status"


class TestRollbackImport:
    def test_import_creates_backup_and_doctor_restores_pre_op(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        backup_dir = _setup(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "keep", "echo keep"])
        before = _backup_count(backup_dir)

        incoming = tmp_path / "incoming.toml"
        doc = tomlkit.document()
        doc.add("version", 1)
        aliases = tomlkit.table()
        t = tomlkit.table()
        t.add("command", "rm -rf /tmp")
        aliases.add("danger", t)
        doc.add("aliases", aliases)
        incoming.write_text(tomlkit.dumps(doc), encoding="utf-8")

        result = runner.invoke(app, ["import", str(incoming), "--overwrite", "--yes"])
        assert result.exit_code == 0, result.output
        after = _backup_count(backup_dir)
        assert after == before + 1

        _corrupt_store(tmp_path)
        data = _restore_and_load(tmp_path)
        assert "keep" in data.aliases
        assert "danger" not in data.aliases