"""Tests for the import command."""

from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()


class TestImportPaths:
    def test_import_merge_conflict_display(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        out = tmp_path / "export.json"
        runner.invoke(app, ["export", str(out)])
        with patch("qwik.commands.importer.prompt_confirm", return_value=False):
            result = runner.invoke(app, ["import", str(out)])
            assert result.exit_code == 0
            assert "Conflicts" in result.output

    def test_import_conflict_display(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        out = tmp_path / "export.json"
        runner.invoke(app, ["export", str(out)])
        with patch("qwik.commands.importer.prompt_confirm", return_value=True):
            result = runner.invoke(app, ["import", str(out)])
            assert result.exit_code == 0
            assert "Conflicts" in result.output
