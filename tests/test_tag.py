"""Tests for the tag and untag commands."""

from __future__ import annotations

from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()


class TestTagUntag:
    def test_untag_noop(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["untag", "gs", "missing"])
        assert result.exit_code == 0

    def test_retag_noop(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        runner.invoke(app, ["tag", "gs", "git"])
        result = runner.invoke(app, ["tag", "gs", "git"])
        assert result.exit_code == 0

    def test_tag_present_noop(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status", "--tag", "git"])
        result = runner.invoke(app, ["tag", "gs", "git"])
        assert result.exit_code == 0
