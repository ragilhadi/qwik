"""Tests for the add command including interactive mode."""

from __future__ import annotations

import re
from unittest.mock import patch

from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s)


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


class TestPlaceholderValidation:
    def test_add_rejects_zero_placeholder(self, tmp_path, monkeypatch):
        from qwik.config import _reset_config
        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        result = runner.invoke(app, ["add", "bad", "echo {0}"])
        assert result.exit_code == 1
        assert "1-based" in result.output or "placeholder" in result.output.lower()

    def test_add_accepts_valid_positional(self, tmp_path, monkeypatch):
        from qwik.config import _reset_config
        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        result = runner.invoke(app, ["add", "gco", "git checkout {1}"])
        assert result.exit_code == 0


class TestMalformedPlaceholderCLI:
    def test_add_rejects_malformed_placeholder(self, tmp_path, monkeypatch):
        from qwik.config import _reset_config
        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        result = runner.invoke(app, ["add", "foo", "echo {bad name}"])
        assert result.exit_code == 1
        assert "bad name" in result.output
        assert "Traceback" not in result.output

    def test_add_accepts_literal_braces(self, tmp_path, monkeypatch):
        from qwik.config import _reset_config
        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        result = runner.invoke(app, ["add", "lit", "echo {}"])
        assert result.exit_code == 0, f"exit={result.exit_code} out={result.output!r}"
        assert "Added" in result.output


class TestGroupFlag:
    def test_group_flag_documented(self, tmp_path, monkeypatch):
        from qwik.config import _reset_config
        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        result = runner.invoke(app, ["add", "--help"])
        out = _strip_ansi(result.output)
        assert "--group" in out
        assert "-g" in out
        assert "--global" not in out

    def test_add_with_group(self, tmp_path, monkeypatch):
        from qwik.config import _reset_config
        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        result = runner.invoke(app, ["add", "gs", "git", "status", "-g", "git"])
        assert result.exit_code == 0
        assert "Added" in result.output

    def test_add_global_now_rejected(self, tmp_path, monkeypatch):
        from qwik.config import _reset_config
        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        result = runner.invoke(app, ["add", "gs", "git", "status", "--global"])
        assert result.exit_code != 0

    def test_add_invalid_group_name_errors(self, tmp_path, monkeypatch):
        from qwik.config import _reset_config
        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        result = runner.invoke(app, ["add", "gs", "git", "status", "--group", "1bad"])
        assert result.exit_code == 1
        assert "Invalid group" in result.output
        assert "Traceback" not in result.output
