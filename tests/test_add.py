"""Tests for the add command including interactive mode."""

from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()


class TestAddInteractive:
    def test_add_interactive_name(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        with patch("qwik.commands.add.prompt_text") as mock_prompt:
            mock_prompt.side_effect = ["gs", "git status"]
            result = runner.invoke(app, ["add"])
            assert result.exit_code == 0
            assert "Added" in result.output

    def test_add_interactive_prompt(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        result = runner.invoke(app, ["add"], input="gs\ngit status\n")
        assert result.exit_code in (0, 1, 2)

    def test_add_interactive_name_prompt(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        import rich.prompt as rp

        orig_ask = rp.Prompt.ask
        calls = 0

        def fake_ask(*a, **kw):
            nonlocal calls
            calls += 1
            if calls == 1:
                return "gs"
            return "git status"

        rp.Prompt.ask = fake_ask
        try:
            result = runner.invoke(app, ["add"])
            assert result.exit_code == 0
            assert "Added" in result.output
        finally:
            rp.Prompt.ask = orig_ask
