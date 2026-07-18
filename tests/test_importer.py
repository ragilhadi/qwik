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


class TestImportSafety:
    def test_import_malformed_toml_friendly_error(self, tmp_path, monkeypatch):
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        bad = tmp_path / "bad.toml"
        bad.write_text("not = valid = toml", encoding="utf-8")
        result = runner.invoke(app, ["import", str(bad), "--yes"])
        assert result.exit_code == 1
        assert "could not parse" in result.output.lower() or "toml" in result.output.lower()

    def test_import_shows_command_preview(self, tmp_path, monkeypatch):
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "danger", "rm -rf /tmp"])
        src = tmp_path / "src.toml"
        runner.invoke(app, ["export", str(src)])
        # Wipe store so import shows everything as new and the command preview surfaces
        (tmp_path / "aliases.toml").unlink()
        _reset_config()
        result = runner.invoke(app, ["import", str(src)], input="n\n")
        assert "rm -rf /tmp" in result.output
        assert result.exit_code == 0  # declined → exit 0
