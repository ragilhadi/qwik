"""Tests for the export command."""

from __future__ import annotations

from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()


class TestExportPaths:
    def test_export_empty(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        out = tmp_path / "export.toml"
        result = runner.invoke(app, ["export", str(out)])
        assert result.exit_code == 1
        assert "No aliases to export" in result.output

    def test_export_unknown_format(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        out = tmp_path / "export.yaml"
        result = runner.invoke(app, ["export", str(out)])
        assert result.exit_code == 1
        assert "Unknown format" in result.output
