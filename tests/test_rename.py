"""Tests for the rename command."""

from __future__ import annotations

from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()


class TestRenamePaths:
    def test_rename_builtin_warning(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["rename", "gs", "cd"])
        assert result.exit_code == 1
        assert "shell builtin" in result.output

    def test_rename_invalid_target(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["rename", "gs", "123bad"])
        assert result.exit_code == 1
        assert "Names must match" in result.output
