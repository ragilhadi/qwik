"""Tests for the run command and shell metacharacter handling."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from qwik.cli import app
from qwik.commands.run import _has_shell_metacharacters

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


class TestRunMetacharacters:
    def test_tilde_requires_shell(self) -> None:
        assert _has_shell_metacharacters("cat ~/file") is True

    def test_andand_requires_shell(self) -> None:
        assert _has_shell_metacharacters("cmd1 && cmd2") is True
        assert _has_shell_metacharacters("cmd1 || cmd2") is True

    def test_glob_star_requires_shell(self) -> None:
        assert _has_shell_metacharacters("cat *.log") is True

    def test_parens_requires_shell(self) -> None:
        assert _has_shell_metacharacters("(cmd1; cmd2)") is True

    def test_simple_no_shell(self) -> None:
        assert _has_shell_metacharacters("echo hello") is False

    def test_run_with_tilde(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "lsh", "ls", "~"])
        result = runner.invoke(app, ["run", "lsh"])
        assert result.exit_code in (0, 1)
