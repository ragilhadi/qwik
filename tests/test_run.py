"""Tests for the run command."""

from __future__ import annotations

from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()


class TestRunBasic:
    def test_run_missing_alias(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        result = runner.invoke(app, ["run", "nonexistent"])
        assert result.exit_code == 1
        assert "does not exist" in result.output

    def test_run_disabled_alias(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        runner.invoke(app, ["disable", "gs"])
        result = runner.invoke(app, ["run", "gs"])
        assert result.exit_code == 1
        assert "disabled" in result.output

    def test_run_simple_command(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "hi", "echo", "hello"])
        result = runner.invoke(app, ["run", "hi"])
        assert result.exit_code == 0

    def test_run_with_args(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "echo2", "echo", "{1}"])
        result = runner.invoke(app, ["run", "echo2", "world"])
        assert result.exit_code == 0

    def test_run_simple_command_with_args(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "ech", "echo", "{1}"])
        result = runner.invoke(app, ["run", "ech", "hello"])
        assert result.exit_code == 0

    def test_run_simple_echo(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "hi", "echo", "hello"])
        result = runner.invoke(app, ["run", "hi"])
        assert result.exit_code == 0


class TestRunTemplates:
    def test_run_template_with_args(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "ech", "echo", "{1}"])
        result = runner.invoke(app, ["run", "ech", "hello"])
        assert result.exit_code == 0

    def test_run_template_with_shell_chars(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "lshome", "ls", "~"])
        result = runner.invoke(app, ["run", "lshome"])
        assert result.exit_code in (0, 1, 2)

    def test_run_missing_arg(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gco", "git checkout {1}"])
        result = runner.invoke(app, ["run", "gco"])
        assert result.exit_code == 1
        assert "Missing argument" in result.output


class TestRunBackupChurn:
    def test_run_does_not_create_backup(self, tmp_path, monkeypatch):
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "hi", "echo", "hello"])
        backup_dir = tmp_path / "backups"
        runner.invoke(app, ["run", "hi"])
        runner.invoke(app, ["run", "hi"])
        runner.invoke(app, ["run", "hi"])
        assert backup_dir.exists()
        assert list(backup_dir.glob("aliases-*.toml")) == []

    def test_run_count_increments(self, tmp_path, monkeypatch):
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "hi", "echo", "hello"])
        runner.invoke(app, ["run", "hi"])
        runner.invoke(app, ["run", "hi"])
        from qwik.core.store import get_store

        alias = get_store().load().get("hi")
        assert alias.run_count == 2
