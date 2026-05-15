"""Tests for the remove command."""

from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()


class TestRemovePaths:
    def test_remove_confirm_no_input(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        with patch("qwik.commands.remove.prompt_confirm", return_value=False):
            result = runner.invoke(app, ["rm", "gs"])
            assert result.exit_code == 0
